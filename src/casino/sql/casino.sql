-- casino/sql/casino.sql
-- Casino schema using bbsengine6 bank module
-- Must run after bbsengine6/sql/bank.sql

\echo schema
\i schema.sql

\echo player
\i player.sql
\echo player_view
\i player_view.sql

\echo table
\i table.sql
\echo table_view
\i table_view.sql
\echo table_map
\i table_map.sql
\echo table_shoe_migration
\i table_shoe_migration.sql

\echo game
\i game.sql
\echo game_view
\i game_view.sql
\echo mapgameplayer
\i mapgameplayer.sql

\echo account
\i account.sql
\echo account_view
\i account_view.sql

\echo betlog
\i betlog.sql
\echo betlog_view
\i betlog_view.sql

\echo log
\i log.sql
\echo log_view
\i log_view.sql

\echo hand
\i hand.sql
\echo hand_view
\i hand_view.sql
