-- casino/scripts/poker.sql
-- Poker game database schema
-- Run this as a superuser: psql -d zoid6 -U postgres -f poker.sql

-- Create poker-specific tables in casino schema

-- Poker tables configuration
CREATE TABLE IF NOT EXISTS casino.__poker_table (
    id SERIAL PRIMARY KEY,
    moniker VARCHAR(50) UNIQUE NOT NULL,
    table_name VARCHAR(100),
    variant VARCHAR(50) NOT NULL DEFAULT 'texas_hold_em',
    betting_structure VARCHAR(20) NOT NULL DEFAULT 'no_limit',
    small_blind INTEGER NOT NULL DEFAULT 1,
    big_blind INTEGER NOT NULL DEFAULT 2,
    min_players INTEGER NOT NULL DEFAULT 2,
    max_players INTEGER NOT NULL DEFAULT 10,
    min_buy_in INTEGER NOT NULL DEFAULT 100,
    max_buy_in INTEGER NOT NULL DEFAULT 10000,
    current_dealer_position INTEGER DEFAULT 0,
    pot INTEGER DEFAULT 0,
    current_bet INTEGER DEFAULT 0,
    current_street VARCHAR(20) DEFAULT 'preflop',
    game_stage VARCHAR(20) DEFAULT 'waiting',
    community_cards TEXT[],
    deck_state TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Poker hands (individual hands within a game)
CREATE TABLE IF NOT EXISTS casino.__poker_hand (
    id SERIAL PRIMARY KEY,
    game_id INTEGER REFERENCES casino.__game(id),
    table_moniker VARCHAR(50) REFERENCES casino.__poker_table(moniker),
    hand_number INTEGER NOT NULL,
    dealer_position INTEGER NOT NULL,
    small_blind_moniker VARCHAR(50),
    big_blind_moniker VARCHAR(50),
    pot_amount INTEGER DEFAULT 0,
    community_cards TEXT[],
    winning_moniker VARCHAR(50),
    winning_hand_rank INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Player hands at showdown
CREATE TABLE IF NOT EXISTS casino.__poker_player_hand (
    id SERIAL PRIMARY KEY,
    hand_id INTEGER REFERENCES casino.__poker_hand(id),
    player_moniker VARCHAR(50) NOT NULL,
    hole_cards TEXT[] NOT NULL,
    best_five_cards TEXT[],
    hand_rank INTEGER NOT NULL,
    is_winner BOOLEAN DEFAULT FALSE,
    winnings INTEGER DEFAULT 0
);

-- Bets placed during each street
CREATE TABLE IF NOT EXISTS casino.__poker_bet (
    id SERIAL PRIMARY KEY,
    hand_id INTEGER REFERENCES casino.__poker_hand(id),
    player_moniker VARCHAR(50) NOT NULL,
    street VARCHAR(20) NOT NULL,
    action VARCHAR(20) NOT NULL,
    amount INTEGER NOT NULL,
    is_all_in BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pots and side pots
CREATE TABLE IF NOT EXISTS casino.__poker_pot (
    id SERIAL PRIMARY KEY,
    hand_id INTEGER REFERENCES casino.__poker_hand(id),
    pot_number INTEGER DEFAULT 0,
    amount INTEGER NOT NULL,
    eligible_players TEXT[],
    winning_players TEXT[],
    awarded_amount INTEGER DEFAULT 0
);

-- Player session at a poker table
CREATE TABLE IF NOT EXISTS casino.__poker_seat (
    id SERIAL PRIMARY KEY,
    table_moniker VARCHAR(50) REFERENCES casino.__poker_table(moniker),
    player_moniker VARCHAR(50) NOT NULL,
    seat_number INTEGER NOT NULL,
    buy_in_amount INTEGER DEFAULT 0,
    current_credits INTEGER DEFAULT 0,
    is_sitting_out BOOLEAN DEFAULT FALSE,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_action_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_moniker, player_moniker)
);

-- Poker game statistics per player
CREATE TABLE IF NOT EXISTS casino.__poker_stats (
    id SERIAL PRIMARY KEY,
    player_moniker VARCHAR(50) NOT NULL UNIQUE,
    hands_played INTEGER DEFAULT 0,
    hands_won INTEGER DEFAULT 0,
    hands_lost INTEGER DEFAULT 0,
    total_winnings INTEGER DEFAULT 0,
    total_loss INTEGER DEFAULT 0,
    big_blinds_won INTEGER DEFAULT 0,
    big_blinds_lost INTEGER DEFAULT 0,
    showdowns_seen INTEGER DEFAULT 0,
    vpip_count INTEGER DEFAULT 0,  -- Voluntarily Put Money In Pot
    pfr_count INTEGER DEFAULT 0,  -- Preflop Raise
    threebet_count INTEGER DEFAULT 0,
    fourbet_count INTEGER DEFAULT 0,
    cbet_count INTEGER DEFAULT 0,  -- Continuation bet
    fold_to_cbet_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_poker_table_moniker ON casino.__poker_table(moniker);
CREATE INDEX IF NOT EXISTS idx_poker_hand_table ON casino.__poker_hand(table_moniker);
CREATE INDEX IF NOT EXISTS idx_poker_hand_game ON casino.__poker_hand(game_id);
CREATE INDEX IF NOT EXISTS idx_poker_player_hand_hand ON casino.__poker_player_hand(hand_id);
CREATE INDEX IF NOT EXISTS idx_poker_player_hand_player ON casino.__poker_player_hand(player_moniker);
CREATE INDEX IF NOT EXISTS idx_poker_bet_hand ON casino.__poker_bet(hand_id);
CREATE INDEX IF NOT EXISTS idx_poker_bet_player ON casino.__poker_bet(player_moniker);
CREATE INDEX IF NOT EXISTS idx_poker_seat_table ON casino.__poker_seat(table_moniker);
CREATE INDEX IF NOT EXISTS idx_poker_seat_player ON casino.__poker_seat(player_moniker);
CREATE INDEX IF NOT EXISTS idx_poker_stats_player ON casino.__poker_stats(player_moniker);

-- Grant permissions to opencode user
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA casino TO opencode;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA casino TO opencode;

-- Add poker variant and betting structure to existing table if not present
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'casino' 
        AND table_name = '__table' 
        AND column_name = 'poker_variant'
    ) THEN
        ALTER TABLE casino.__table ADD COLUMN poker_variant VARCHAR(50);
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'casino' 
        AND table_name = '__table' 
        AND column_name = 'betting_structure'
    ) THEN
        ALTER TABLE casino.__table ADD COLUMN betting_structure VARCHAR(20);
    END IF;
END $$;
