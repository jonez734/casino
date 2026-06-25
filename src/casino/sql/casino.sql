-- casino/sql/casino.sql
-- Casino schema using bbsengine6 bank module
-- Must run after bbsengine6/sql/bank.sql

\echo schema
\i schema.sql

\echo player
\i player.sql
\echo player_view
\i player_view.sql

\echo bank
\i /home/opencode/data/work/bbsengine6/py/src/bbsengine6/sql/bank.sql

\echo bank_table
\i bank_table.sql
\echo bank_player
\i bank_player.sql

\echo table
\i table.sql
\echo table_view
\i table_view.sql
\echo table_map
\i map_cardtable_player.sql
\echo table_shoe_migration
\i table_shoe_migration.sql

\echo bank_migration
\i bank_migration.sql

\echo game
\i game.sql
\echo mapgameplayer
\i map_game_player.sql
\echo game_view
\i game_view.sql

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

\echo slots
\i slots.sql
\echo slot_spin_view
\i slot_spin_view.sql
