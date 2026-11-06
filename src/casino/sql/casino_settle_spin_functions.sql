-- casino/sql/casino_settle_spin_functions.sql
-- Settles one slots spin in a single transaction: the bank move, the casino.__slot_spin audit row,
-- and the player's stats. Casino owns this function because the spin, its audit row, and its stats
-- must commit together; splitting them across bed would break that atomicity.
--
-- The acting moniker comes from the verified token row (engine.__bed_token), never from the request.
-- The caller passes the net (payout minus bet) and the spin payload. The function refuses a net that
-- does not match the request's own bet and payout, and it refuses an overdraft. Insufficient funds
-- and bad input are returned as jsonb codes, so the caller keeps its existing error codes; only a
-- missing session raises.
--
-- Installed by ``casino --install`` after casino_op_functions.sql. Idempotent.
-- Granted to bed_zoid6, the daemon's login role (see zoid6 INSTALL.md section 4a).

CREATE OR REPLACE FUNCTION engine.casino_settle_spin(p_token_hash bytea, p_args jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = engine, public, pg_temp
AS $$
DECLARE
    v_actor citext;
    v_table citext;
    v_bet numeric;
    v_payout numeric;
    v_net numeric;
    v_reels jsonb;
    v_wins jsonb;
    v_account bigint;
    v_balance numeric;
    v_spin_id bigint;
    v_corr text;
    v_desc text;
    v_existing_id bigint;
    v_existing_balance numeric;
    v_existing_bet numeric;
    v_existing_payout numeric;
    v_existing_reels jsonb;
    v_existing_wins jsonb;
    v_existing_table citext;
BEGIN
    SELECT t.moniker INTO v_actor
    FROM engine.__bed_token t
    WHERE t.token_hash = p_token_hash AND t.expires_at > now();
    IF v_actor IS NULL THEN
        RAISE EXCEPTION 'casino_settle_spin: no live session for this token';
    END IF;

    v_table := p_args->>'table_moniker';
    v_bet := (p_args->>'bet')::numeric;
    v_payout := (p_args->>'payout')::numeric;
    v_net := (p_args->>'net')::numeric;
    v_reels := coalesce(p_args->'reels', '[]'::jsonb);
    v_wins := coalesce(p_args->'wins', '[]'::jsonb);
    v_corr := coalesce(p_args->>'correlation_id', '');

    IF v_table IS NULL OR v_bet IS NULL OR v_bet <= 0 OR v_payout IS NULL OR v_payout < 0 THEN
        RETURN jsonb_build_object('success', false, 'code', 'invalid_request',
                                  'message', 'table, a positive bet, and a non-negative payout are required');
    END IF;
    IF v_net IS DISTINCT FROM (v_payout - v_bet) THEN
        RETURN jsonb_build_object('success', false, 'code', 'invalid_request',
                                  'message', 'net must equal payout minus bet');
    END IF;

    SELECT id, balance INTO v_account, v_balance
    FROM bank.__account WHERE moniker = v_actor FOR UPDATE;
    IF v_account IS NULL THEN
        RETURN jsonb_build_object('success', false, 'code', 'insufficient_funds',
                                  'message', 'Account not found');
    END IF;

    -- Dedupe on the correlation id while holding the account lock, so two concurrent retries of
    -- the same spin cannot both pass this check. A retry returns the first settlement's result and
    -- moves no money. The check runs before any balance change.
    IF v_corr <> '' THEN
        SELECT s.id, s.table_moniker, s.bet, s.payout, s.reels, s.wins
          INTO v_existing_id, v_existing_table, v_existing_bet, v_existing_payout,
               v_existing_reels, v_existing_wins
        FROM casino.__slot_spin s
        WHERE s.correlation_id = v_corr AND s.player_moniker = v_actor;
        IF v_existing_id IS NOT NULL THEN
            -- A retry of a spin that already settled. Return the stored spin, not an error, so the
            -- player sees the result of the spin they paid for. No money moves.
            SELECT balance INTO v_existing_balance FROM bank.__account WHERE id = v_account;
            RETURN jsonb_build_object(
                'success', true,
                'duplicate', true,
                'spin_id', v_existing_id,
                'new_balance', v_existing_balance,
                'table_moniker', v_existing_table,
                'bet', v_existing_bet,
                'payout', v_existing_payout,
                'net', v_existing_payout - v_existing_bet,
                'reels', v_existing_reels,
                'wins', v_existing_wins
            );
        END IF;
    END IF;
    IF v_net < 0 AND v_balance < -v_net THEN
        RETURN jsonb_build_object('success', false, 'code', 'insufficient_funds',
                                  'message', 'Insufficient funds');
    END IF;

    IF v_net <> 0 THEN
        UPDATE bank.__account SET balance = balance + v_net
        WHERE id = v_account
        RETURNING balance INTO v_balance;

        IF v_net > 0 THEN
            v_desc := 'Slots spin payout at ' || v_table || ' (spin corr=' || v_corr || ')';
            INSERT INTO bank.__transaction
                (accountid, amount, transactiontype, description, membermoniker)
            VALUES (v_account, v_net, 'slots_payout', v_desc, v_actor);
        ELSE
            v_desc := 'Slots spin debit at ' || v_table || ' (spin corr=' || v_corr || ')';
            INSERT INTO bank.__transaction
                (accountid, amount, transactiontype, description, membermoniker)
            VALUES (v_account, v_net, 'slots_bet', v_desc, v_actor);
        END IF;
    END IF;

    INSERT INTO casino.__slot_spin
        (table_moniker, player_moniker, bet, payout, reels, wins, correlation_id)
    VALUES (v_table, v_actor, v_bet, v_payout, v_reels, v_wins, NULLIF(v_corr, ''))
    RETURNING id INTO v_spin_id;

    UPDATE casino.__player
    SET stats = stats || jsonb_build_object(
        'slots.spins', COALESCE((stats->>'slots.spins')::int, 0) + 1,
        'slots.wins',  COALESCE((stats->>'slots.wins')::int, 0) + CASE WHEN v_payout > 0 THEN 1 ELSE 0 END,
        'slots.net',   COALESCE((stats->>'slots.net')::int, 0) + v_net::int
    )
    WHERE moniker = v_actor;

    IF v_payout > 0 THEN
        UPDATE casino.__player
        SET stats = stats || jsonb_build_object(
            'slots.biggest_win',
            GREATEST(COALESCE((stats->>'slots.biggest_win')::int, 0), v_payout::int)
        )
        WHERE moniker = v_actor;
    END IF;

    RETURN jsonb_build_object(
        'success', true,
        'duplicate', false,
        'spin_id', v_spin_id,
        'new_balance', v_balance,
        'table_moniker', v_table,
        'bet', v_bet,
        'payout', v_payout,
        'net', v_net,
        'reels', v_reels,
        'wins', v_wins
    );
END;
$$;

ALTER FUNCTION engine.casino_settle_spin(bytea, jsonb) OWNER TO zoid6;
REVOKE ALL ON FUNCTION engine.casino_settle_spin(bytea, jsonb) FROM PUBLIC;
-- The daemon logs in as bed_zoid6 (NOINHERIT), so the grant names that login directly.
-- Casino's slots connections use the same login (casino/dal/conn.py keeps the login role).
GRANT EXECUTE ON FUNCTION engine.casino_settle_spin(bytea, jsonb) TO bed_zoid6;
