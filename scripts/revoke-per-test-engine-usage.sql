-- revoke-per-test-engine-usage.sql
--
-- Removes the USAGE grants that per-test casino roles hold on the LIVE schema engine in zoid6.
-- Those grants were added by test runs against the live database. They are not production
-- privileges, and the test suites now refuse to run against zoid6.
--
-- Scope, checked before this file was written: the 190 roles listed below are the only
-- per-test roles with USAGE on engine in zoid6. Every other grantee on engine (bed, bed_zoid6,
-- member, web, term, sysop, zoid6, m_opencode, m_jam, m_lo_test, m_bjbed_a, m_bjbed_b) is left
-- untouched, and the script refuses to revoke from any role outside the per-test families.
--
-- Run as jam (superuser) against zoid6, once, after review:
--
--   psql -U jam -d zoid6 -v ON_ERROR_STOP=1 -1 -f scripts/revoke-per-test-engine-usage.sql
--
-- -1 runs it in one transaction: any error rolls back all of it.
-- Idempotent: once revoked, a second run revokes nothing and reports 0 remaining.
--
-- A revoke run by anyone other than the grantor (postgres) or a superuser does nothing and
-- only warns "no privileges could be revoked". The final check turns that into an error, so
-- a run that did not take effect fails and rolls back. Run it as jam.

\set ON_ERROR_STOP on

-- Guard: only the live database this was written for.
do $$
begin
    if current_database() <> 'zoid6' then
        raise exception 'revoke-per-test-engine-usage: refusing to run against %, only zoid6',
            current_database();
    end if;
end
$$;

revoke usage on schema engine from m_bj2p_a_039cb70f;
revoke usage on schema engine from m_bj2p_a_130cf7ec;
revoke usage on schema engine from m_bj2p_a_1da60a3c;
revoke usage on schema engine from m_bj2p_a_2e3a3fa6;
revoke usage on schema engine from m_bj2p_a_33e5acd6;
revoke usage on schema engine from m_bj2p_a_3a23a3cf;
revoke usage on schema engine from m_bj2p_a_3c44c05f;
revoke usage on schema engine from m_bj2p_a_455379ff;
revoke usage on schema engine from m_bj2p_a_46ce8090;
revoke usage on schema engine from m_bj2p_a_47604aff;
revoke usage on schema engine from m_bj2p_a_4ceb62f3;
revoke usage on schema engine from m_bj2p_a_6191ec6e;
revoke usage on schema engine from m_bj2p_a_6503705f;
revoke usage on schema engine from m_bj2p_a_67d96383;
revoke usage on schema engine from m_bj2p_a_6f562620;
revoke usage on schema engine from m_bj2p_a_787ad847;
revoke usage on schema engine from m_bj2p_a_84b2b9ae;
revoke usage on schema engine from m_bj2p_a_852fa5c4;
revoke usage on schema engine from m_bj2p_a_85ea92eb;
revoke usage on schema engine from m_bj2p_a_8aabb2b8;
revoke usage on schema engine from m_bj2p_a_8e68b96d;
revoke usage on schema engine from m_bj2p_a_902bdf9c;
revoke usage on schema engine from m_bj2p_a_95ab9ded;
revoke usage on schema engine from m_bj2p_a_9950f341;
revoke usage on schema engine from m_bj2p_a_a59c2aab;
revoke usage on schema engine from m_bj2p_a_b2eb80d4;
revoke usage on schema engine from m_bj2p_a_bfe48c34;
revoke usage on schema engine from m_bj2p_a_c77fd8ee;
revoke usage on schema engine from m_bj2p_a_c914e80f;
revoke usage on schema engine from m_bj2p_a_d0d49e49;
revoke usage on schema engine from m_bj2p_a_d0f0643e;
revoke usage on schema engine from m_bj2p_a_d5d2b90a;
revoke usage on schema engine from m_bj2p_a_dd056b98;
revoke usage on schema engine from m_bj2p_a_e8a3e4cf;
revoke usage on schema engine from m_bj2p_a_e9d37400;
revoke usage on schema engine from m_bj2p_a_ed0375b6;
revoke usage on schema engine from m_bj2p_a_f4a4b1ec;
revoke usage on schema engine from m_bj2p_a_fd19c80b;
revoke usage on schema engine from m_bj2p_b_039cb70f;
revoke usage on schema engine from m_bj2p_b_130cf7ec;
revoke usage on schema engine from m_bj2p_b_1da60a3c;
revoke usage on schema engine from m_bj2p_b_2e3a3fa6;
revoke usage on schema engine from m_bj2p_b_33e5acd6;
revoke usage on schema engine from m_bj2p_b_3a23a3cf;
revoke usage on schema engine from m_bj2p_b_3c44c05f;
revoke usage on schema engine from m_bj2p_b_455379ff;
revoke usage on schema engine from m_bj2p_b_46ce8090;
revoke usage on schema engine from m_bj2p_b_47604aff;
revoke usage on schema engine from m_bj2p_b_4ceb62f3;
revoke usage on schema engine from m_bj2p_b_6191ec6e;
revoke usage on schema engine from m_bj2p_b_6503705f;
revoke usage on schema engine from m_bj2p_b_67d96383;
revoke usage on schema engine from m_bj2p_b_6f562620;
revoke usage on schema engine from m_bj2p_b_787ad847;
revoke usage on schema engine from m_bj2p_b_84b2b9ae;
revoke usage on schema engine from m_bj2p_b_852fa5c4;
revoke usage on schema engine from m_bj2p_b_85ea92eb;
revoke usage on schema engine from m_bj2p_b_8aabb2b8;
revoke usage on schema engine from m_bj2p_b_8e68b96d;
revoke usage on schema engine from m_bj2p_b_902bdf9c;
revoke usage on schema engine from m_bj2p_b_95ab9ded;
revoke usage on schema engine from m_bj2p_b_9950f341;
revoke usage on schema engine from m_bj2p_b_a59c2aab;
revoke usage on schema engine from m_bj2p_b_b2eb80d4;
revoke usage on schema engine from m_bj2p_b_bfe48c34;
revoke usage on schema engine from m_bj2p_b_c77fd8ee;
revoke usage on schema engine from m_bj2p_b_c914e80f;
revoke usage on schema engine from m_bj2p_b_d0d49e49;
revoke usage on schema engine from m_bj2p_b_d0f0643e;
revoke usage on schema engine from m_bj2p_b_d5d2b90a;
revoke usage on schema engine from m_bj2p_b_dd056b98;
revoke usage on schema engine from m_bj2p_b_e8a3e4cf;
revoke usage on schema engine from m_bj2p_b_e9d37400;
revoke usage on schema engine from m_bj2p_b_ed0375b6;
revoke usage on schema engine from m_bj2p_b_f4a4b1ec;
revoke usage on schema engine from m_bj2p_b_fd19c80b;
revoke usage on schema engine from m_bjconsole_0979215b;
revoke usage on schema engine from m_bjconsole_0ba4a3fa;
revoke usage on schema engine from m_bjconsole_107ee2d2;
revoke usage on schema engine from m_bjconsole_11812c14;
revoke usage on schema engine from m_bjconsole_15fa7b27;
revoke usage on schema engine from m_bjconsole_16537211;
revoke usage on schema engine from m_bjconsole_20a48822;
revoke usage on schema engine from m_bjconsole_20f9081d;
revoke usage on schema engine from m_bjconsole_2109a182;
revoke usage on schema engine from m_bjconsole_24af568e;
revoke usage on schema engine from m_bjconsole_35348f77;
revoke usage on schema engine from m_bjconsole_418f05a3;
revoke usage on schema engine from m_bjconsole_4ee923ae;
revoke usage on schema engine from m_bjconsole_521aff18;
revoke usage on schema engine from m_bjconsole_526a8609;
revoke usage on schema engine from m_bjconsole_55fc7b4d;
revoke usage on schema engine from m_bjconsole_5b5cd20d;
revoke usage on schema engine from m_bjconsole_5d0da60d;
revoke usage on schema engine from m_bjconsole_7a9299c7;
revoke usage on schema engine from m_bjconsole_7f6be124;
revoke usage on schema engine from m_bjconsole_83ea196d;
revoke usage on schema engine from m_bjconsole_84418935;
revoke usage on schema engine from m_bjconsole_a0964c65;
revoke usage on schema engine from m_bjconsole_a9ca5b77;
revoke usage on schema engine from m_bjconsole_a_00f7c2cc;
revoke usage on schema engine from m_bjconsole_a_02cc0126;
revoke usage on schema engine from m_bjconsole_a_031acb64;
revoke usage on schema engine from m_bjconsole_a_033634a1;
revoke usage on schema engine from m_bjconsole_a_1817da31;
revoke usage on schema engine from m_bjconsole_a_1a11eb1d;
revoke usage on schema engine from m_bjconsole_a_1fa3bd13;
revoke usage on schema engine from m_bjconsole_a_20111dca;
revoke usage on schema engine from m_bjconsole_a_2d3414a5;
revoke usage on schema engine from m_bjconsole_a_3079d254;
revoke usage on schema engine from m_bjconsole_a_32a9ec0b;
revoke usage on schema engine from m_bjconsole_a_4655db1c;
revoke usage on schema engine from m_bjconsole_a_47813890;
revoke usage on schema engine from m_bjconsole_a_49f9cd91;
revoke usage on schema engine from m_bjconsole_a_5767e668;
revoke usage on schema engine from m_bjconsole_a_62c1bdfc;
revoke usage on schema engine from m_bjconsole_a_65091dd5;
revoke usage on schema engine from m_bjconsole_a_6b8b5ef0;
revoke usage on schema engine from m_bjconsole_a_70891b32;
revoke usage on schema engine from m_bjconsole_a_721ab4dc;
revoke usage on schema engine from m_bjconsole_a_731fc2e4;
revoke usage on schema engine from m_bjconsole_a_79156924;
revoke usage on schema engine from m_bjconsole_a_7d4401b3;
revoke usage on schema engine from m_bjconsole_a_8112485a;
revoke usage on schema engine from m_bjconsole_a_8127eaee;
revoke usage on schema engine from m_bjconsole_a_87e7d85f;
revoke usage on schema engine from m_bjconsole_a_a06fbd8e;
revoke usage on schema engine from m_bjconsole_a_a62ed963;
revoke usage on schema engine from m_bjconsole_a_aa610eb5;
revoke usage on schema engine from m_bjconsole_a_b131dc99;
revoke usage on schema engine from m_bjconsole_a_b8664757;
revoke usage on schema engine from m_bjconsole_a_c43f2aa5;
revoke usage on schema engine from m_bjconsole_a_c65f0965;
revoke usage on schema engine from m_bjconsole_a_d2d2a621;
revoke usage on schema engine from m_bjconsole_a_e25ab0de;
revoke usage on schema engine from m_bjconsole_a_e460e54e;
revoke usage on schema engine from m_bjconsole_a_e84680db;
revoke usage on schema engine from m_bjconsole_a_f38fe519;
revoke usage on schema engine from m_bjconsole_b3a78174;
revoke usage on schema engine from m_bjconsole_b873c6cf;
revoke usage on schema engine from m_bjconsole_b9223f92;
revoke usage on schema engine from m_bjconsole_b9d1fb97;
revoke usage on schema engine from m_bjconsole_b_00f7c2cc;
revoke usage on schema engine from m_bjconsole_b_02cc0126;
revoke usage on schema engine from m_bjconsole_b_031acb64;
revoke usage on schema engine from m_bjconsole_b_033634a1;
revoke usage on schema engine from m_bjconsole_b_1817da31;
revoke usage on schema engine from m_bjconsole_b_1a11eb1d;
revoke usage on schema engine from m_bjconsole_b_1fa3bd13;
revoke usage on schema engine from m_bjconsole_b_20111dca;
revoke usage on schema engine from m_bjconsole_b_2d3414a5;
revoke usage on schema engine from m_bjconsole_b_3079d254;
revoke usage on schema engine from m_bjconsole_b_32a9ec0b;
revoke usage on schema engine from m_bjconsole_b_4655db1c;
revoke usage on schema engine from m_bjconsole_b_47813890;
revoke usage on schema engine from m_bjconsole_b_49f9cd91;
revoke usage on schema engine from m_bjconsole_b_5767e668;
revoke usage on schema engine from m_bjconsole_b_62c1bdfc;
revoke usage on schema engine from m_bjconsole_b_65091dd5;
revoke usage on schema engine from m_bjconsole_b_6b8b5ef0;
revoke usage on schema engine from m_bjconsole_b_70891b32;
revoke usage on schema engine from m_bjconsole_b_721ab4dc;
revoke usage on schema engine from m_bjconsole_b_731fc2e4;
revoke usage on schema engine from m_bjconsole_b_79156924;
revoke usage on schema engine from m_bjconsole_b_7d4401b3;
revoke usage on schema engine from m_bjconsole_b_8112485a;
revoke usage on schema engine from m_bjconsole_b_8127eaee;
revoke usage on schema engine from m_bjconsole_b_87e7d85f;
revoke usage on schema engine from m_bjconsole_b_a06fbd8e;
revoke usage on schema engine from m_bjconsole_b_a62ed963;
revoke usage on schema engine from m_bjconsole_b_aa610eb5;
revoke usage on schema engine from m_bjconsole_b_b131dc99;
revoke usage on schema engine from m_bjconsole_b_b8664757;
revoke usage on schema engine from m_bjconsole_b_c43f2aa5;
revoke usage on schema engine from m_bjconsole_b_c65f0965;
revoke usage on schema engine from m_bjconsole_b_d2d2a621;
revoke usage on schema engine from m_bjconsole_b_e25ab0de;
revoke usage on schema engine from m_bjconsole_b_e460e54e;
revoke usage on schema engine from m_bjconsole_b_e84680db;
revoke usage on schema engine from m_bjconsole_b_f38fe519;
revoke usage on schema engine from m_bjconsole_be15ffbc;
revoke usage on schema engine from m_bjconsole_c06f306e;
revoke usage on schema engine from m_bjconsole_c17df71c;
revoke usage on schema engine from m_bjconsole_c509d713;
revoke usage on schema engine from m_bjconsole_c7c8c46c;
revoke usage on schema engine from m_bjconsole_d1802a42;
revoke usage on schema engine from m_bjconsole_d509092c;
revoke usage on schema engine from m_bjconsole_e1e62028;
revoke usage on schema engine from m_bjconsole_ee077a99;
revoke usage on schema engine from m_bjconsole_f160ac50;

-- Verify: no per-test role may hold USAGE on engine afterwards.
do $$
declare
    left_over integer;
begin
    select count(*) into left_over
    from pg_namespace n
    cross join lateral aclexplode(n.nspacl) a
    join pg_roles r on r.oid = a.grantee
    where n.nspname = 'engine'
      and a.privilege_type = 'USAGE'
      and r.rolname ~ '^(m_)?(bjconsole|bj2p)';
    if left_over > 0 then
        raise exception 'revoke-per-test-engine-usage: % per-test grant(s) remain on engine', left_over;
    end if;
    raise notice 'revoke-per-test-engine-usage: no per-test USAGE remains on engine.';
end
$$;
