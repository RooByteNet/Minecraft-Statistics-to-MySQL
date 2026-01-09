-- Useful database views for the Minecraft statistics database
-- Run this after migration to create convenient views for common queries

USE database;

-- View: Player Summary
-- Shows basic player info with activity status
CREATE OR REPLACE VIEW v_player_summary AS
SELECT
    p.uuid,
    p.name,
    p.first_seen,
    p.last_seen,
    TIMESTAMPDIFF(DAY, p.first_seen, p.last_seen) as days_active,
    TIMESTAMPDIFF(DAY, p.last_seen, NOW()) as days_since_active,
    CASE
        WHEN p.last_seen >= DATE_SUB(NOW(), INTERVAL 7 DAY) THEN 'Active'
        WHEN p.last_seen >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 'Recent'
        WHEN p.last_seen >= DATE_SUB(NOW(), INTERVAL 90 DAY) THEN 'Inactive'
        ELSE 'Dormant'
    END as activity_status
FROM players p;

-- View: Player Stats Count
-- Shows how many different stats each player has in each category
CREATE OR REPLACE VIEW v_player_stats_count AS
SELECT
    p.uuid,
    p.name,
    COUNT(DISTINCT u.stat_key) as items_used,
    COUNT(DISTINCT m.stat_key) as blocks_mined,
    COUNT(DISTINCT b.stat_key) as items_broken,
    COUNT(DISTINCT k.stat_key) as mobs_killed,
    COUNT(DISTINCT c.stat_key) as items_crafted,
    COUNT(DISTINCT d.stat_key) as items_dropped,
    COUNT(DISTINCT kb.stat_key) as killed_by_count,
    COUNT(DISTINCT pu.stat_key) as items_picked_up
FROM players p
LEFT JOIN player_stats_used u ON p.uuid = u.uuid
LEFT JOIN player_stats_mined m ON p.uuid = m.uuid
LEFT JOIN player_stats_broken b ON p.uuid = b.uuid
LEFT JOIN player_stats_killed k ON p.uuid = k.uuid
LEFT JOIN player_stats_crafted c ON p.uuid = c.uuid
LEFT JOIN player_stats_dropped d ON p.uuid = d.uuid
LEFT JOIN player_stats_killed_by kb ON p.uuid = kb.uuid
LEFT JOIN player_stats_picked_up pu ON p.uuid = pu.uuid
GROUP BY p.uuid, p.name;

-- View: Player Mining Totals
-- Shows total blocks mined for each player
CREATE OR REPLACE VIEW v_player_mining_totals AS
SELECT
    p.uuid,
    p.name,
    COALESCE(SUM(m.stat_value), 0) as total_blocks_mined,
    COUNT(DISTINCT m.stat_key) as unique_blocks_mined
FROM players p
LEFT JOIN player_stats_mined m ON p.uuid = m.uuid
GROUP BY p.uuid, p.name;

-- View: Player Kill Totals
-- Shows total mobs killed for each player
CREATE OR REPLACE VIEW v_player_kill_totals AS
SELECT
    p.uuid,
    p.name,
    COALESCE(SUM(k.stat_value), 0) as total_mobs_killed,
    COUNT(DISTINCT k.stat_key) as unique_mobs_killed
FROM players p
LEFT JOIN player_stats_killed k ON p.uuid = k.uuid
GROUP BY p.uuid, p.name;

-- View: Top Miners Leaderboard
-- Top 100 players by blocks mined
CREATE OR REPLACE VIEW v_top_miners AS
SELECT
    p.name,
    SUM(m.stat_value) as total_blocks_mined,
    COUNT(DISTINCT m.stat_key) as unique_blocks,
    p.last_seen
FROM players p
JOIN player_stats_mined m ON p.uuid = m.uuid
GROUP BY p.uuid, p.name, p.last_seen
ORDER BY total_blocks_mined DESC
LIMIT 100;

-- View: Top Warriors Leaderboard
-- Top 100 players by mobs killed
CREATE OR REPLACE VIEW v_top_warriors AS
SELECT
    p.name,
    SUM(k.stat_value) as total_mobs_killed,
    COUNT(DISTINCT k.stat_key) as unique_mobs,
    p.last_seen
FROM players p
JOIN player_stats_killed k ON p.uuid = k.uuid
GROUP BY p.uuid, p.name, p.last_seen
ORDER BY total_mobs_killed DESC
LIMIT 100;

-- View: Top Crafters Leaderboard
-- Top 100 players by items crafted
CREATE OR REPLACE VIEW v_top_crafters AS
SELECT
    p.name,
    SUM(c.stat_value) as total_items_crafted,
    COUNT(DISTINCT c.stat_key) as unique_items,
    p.last_seen
FROM players p
JOIN player_stats_crafted c ON p.uuid = c.uuid
GROUP BY p.uuid, p.name, p.last_seen
ORDER BY total_items_crafted DESC
LIMIT 100;

-- View: Diamond Miners
-- Players ranked by diamond ore mined
CREATE OR REPLACE VIEW v_diamond_miners AS
SELECT
    p.name,
    m.stat_value as diamonds_mined,
    p.last_seen
FROM players p
JOIN player_stats_mined m ON p.uuid = m.uuid
WHERE m.stat_key = 'minecraft:diamond_ore'
ORDER BY m.stat_value DESC;

-- View: Most Active Players
-- Players ranked by recent activity
CREATE OR REPLACE VIEW v_most_active AS
SELECT
    p.uuid,
    p.name,
    p.last_seen,
    TIMESTAMPDIFF(HOUR, p.last_seen, NOW()) as hours_since_active,
    TIMESTAMPDIFF(DAY, p.first_seen, p.last_seen) as days_active
FROM players p
WHERE p.last_seen >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY p.last_seen DESC;

-- View: Comprehensive Player Stats
-- All major stats for each player in one view
CREATE OR REPLACE VIEW v_player_comprehensive AS
SELECT
    p.uuid,
    p.name,
    p.first_seen,
    p.last_seen,
    COALESCE(SUM(m.stat_value), 0) as total_blocks_mined,
    COALESCE(SUM(k.stat_value), 0) as total_mobs_killed,
    COALESCE(SUM(c.stat_value), 0) as total_items_crafted,
    COALESCE(SUM(u.stat_value), 0) as total_items_used,
    COALESCE(SUM(d.stat_value), 0) as total_items_dropped,
    COALESCE(SUM(pu.stat_value), 0) as total_items_picked_up,
    COUNT(DISTINCT m.stat_key) as unique_blocks_mined,
    COUNT(DISTINCT k.stat_key) as unique_mobs_killed,
    COUNT(DISTINCT c.stat_key) as unique_items_crafted
FROM players p
LEFT JOIN player_stats_mined m ON p.uuid = m.uuid
LEFT JOIN player_stats_killed k ON p.uuid = k.uuid
LEFT JOIN player_stats_crafted c ON p.uuid = c.uuid
LEFT JOIN player_stats_used u ON p.uuid = u.uuid
LEFT JOIN player_stats_dropped d ON p.uuid = d.uuid
LEFT JOIN player_stats_picked_up pu ON p.uuid = pu.uuid
GROUP BY p.uuid, p.name, p.first_seen, p.last_seen;

-- View: Popular Items Mined
-- Shows which blocks are most commonly mined across all players
CREATE OR REPLACE VIEW v_popular_items_mined AS
SELECT
    m.stat_key,
    COUNT(DISTINCT m.uuid) as players_mined,
    SUM(m.stat_value) as total_mined,
    AVG(m.stat_value) as avg_per_player,
    MAX(m.stat_value) as highest_by_one_player
FROM player_stats_mined m
GROUP BY m.stat_key
ORDER BY total_mined DESC;

-- View: Popular Mobs Killed
-- Shows which mobs are most commonly killed across all players
CREATE OR REPLACE VIEW v_popular_mobs_killed AS
SELECT
    k.stat_key,
    COUNT(DISTINCT k.uuid) as players_killed,
    SUM(k.stat_value) as total_killed,
    AVG(k.stat_value) as avg_per_player,
    MAX(k.stat_value) as highest_by_one_player
FROM player_stats_killed k
GROUP BY k.stat_key
ORDER BY total_killed DESC;

-- View: Player Deaths
-- Shows how players died (from killed_by stats)
CREATE OR REPLACE VIEW v_player_deaths AS
SELECT
    p.name,
    kb.stat_key as cause_of_death,
    kb.stat_value as death_count,
    p.last_seen
FROM players p
JOIN player_stats_killed_by kb ON p.uuid = kb.uuid
ORDER BY p.name, kb.stat_value DESC;

-- View: New Players
-- Players who joined in the last 30 days
CREATE OR REPLACE VIEW v_new_players AS
SELECT
    p.uuid,
    p.name,
    p.first_seen,
    TIMESTAMPDIFF(DAY, p.first_seen, NOW()) as days_since_joined,
    p.last_seen,
    CASE
        WHEN p.last_seen >= DATE_SUB(NOW(), INTERVAL 7 DAY) THEN 'Active'
        ELSE 'Inactive'
    END as status
FROM players p
WHERE p.first_seen >= DATE_SUB(NOW(), INTERVAL 30 DAY)
ORDER BY p.first_seen DESC;

-- Example queries using the views:

-- Query 1: Get active players summary
-- SELECT * FROM v_player_summary WHERE activity_status = 'Active';

-- Query 2: Get comprehensive stats for a specific player
-- SELECT * FROM v_player_comprehensive WHERE name = 'YourPlayerName';

-- Query 3: Get top 10 miners
-- SELECT * FROM v_top_miners LIMIT 10;

-- Query 4: Get all diamond miners
-- SELECT * FROM v_diamond_miners;

-- Query 5: Get most popular blocks to mine
-- SELECT * FROM v_popular_items_mined LIMIT 20;

-- Query 6: Get player stats count for all players
-- SELECT * FROM v_player_stats_count ORDER BY blocks_mined DESC;

-- Query 7: Find players who haven't played in 60+ days
-- SELECT * FROM v_player_summary
-- WHERE days_since_active > 60
-- ORDER BY last_seen DESC;

-- Query 8: Get new players who are still active
-- SELECT * FROM v_new_players WHERE status = 'Active';

-- Query 9: Compare two players
-- SELECT * FROM v_player_comprehensive
-- WHERE name IN ('Player1', 'Player2');

-- Query 10: Get most dangerous mobs
-- SELECT * FROM v_popular_mobs_killed LIMIT 10;
