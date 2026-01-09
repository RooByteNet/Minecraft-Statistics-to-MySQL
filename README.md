# Minecraft Statistics to MySQL

A Python application that synchronizes Minecraft player statistics from a server to a MySQL database, enabling advanced querying, analytics, and leaderboards.

## Overview

This tool parses Minecraft's JSON stat files and imports them into a structured MySQL database. It supports both local file access and remote SFTP fetching, automatically maintains player information, and creates normalized tables for different stat categories (mining, kills, crafting, etc.).

## Features

- **Automated Stats Sync**: Periodically fetch and sync player statistics to MySQL
- **SFTP Support**: Download stats directly from remote Minecraft servers via SFTP
- **Comprehensive Tracking**: Tracks 9 different stat categories:
  - Items Used
  - Blocks Mined
  - Items Broken
  - Custom Stats (deaths, playtime, jumps, etc.)
  - Mobs Killed
  - Items Crafted
  - Items Dropped
  - Killed By (death causes)
  - Items Picked Up
- **Player Management**: Automatic player UUID to username mapping via usercache.json
- **Database Views**: Pre-built SQL views for leaderboards, analytics, and reporting
- **Foreign Key Relationships**: Proper relational database structure with cascading deletes
- **Incremental Updates**: Efficient upsert operations for continuous synchronization

## Requirements

- Python 3.7+
- MySQL 5.7+ or MariaDB 10.2+
- Minecraft Java Edition server (stats in JSON format)
- SFTP access (optional, for remote servers)

## Installation

### Linux/Ubuntu

1. **Clone or download this repository**

2. **Run the installation script:**
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

   This creates a virtual environment and installs dependencies.

3. **Configure the application** (see Configuration section below)

### Windows

1. **Clone or download this repository**

2. **Create a virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Configure the application** (see Configuration section below)

## Configuration

Edit `config.ini` with your server details:

```ini
[paths]
# Absolute path to your Minecraft world directory (contains the stats folder)
world_path = /path/to/minecraft/world
# Optional temp directory for downloads; leave empty to use system temp
temp_dir =

[mysql]
host = localhost
port = 3306
user = your_mysql_user
password = your_mysql_password
database = minecraft_stats
table = player_stats
used_table = player_stats_used
mined_table = player_stats_mined
broken_table = player_stats_broken
custom_table = player_stats_custom
killed_table = player_stats_killed
crafted_table = player_stats_crafted
dropped_table = player_stats_dropped
killed_by_table = player_stats_killed_by
picked_up_table = player_stats_picked_up

[sftp]
# Set enabled = true to fetch world stats via SFTP into a temp folder before processing
enabled = false
host = your.minecraft.server
port = 22
user = sftp_user
password = sftp_password
# If you know the server root (contains server.properties, usercache.json), set it here
remote_root_path = /minecraft
# World name folder under the server root. The stats live in <remote_root_path>/<world_name>/stats
world_name = world
# If you prefer, set the direct world path instead (fallback if root/name not set)
remote_world_path = /minecraft/world
```

### Configuration Notes

- **Local Mode**: If `sftp.enabled = false`, the tool reads directly from `world_path`
- **SFTP Mode**: If `sftp.enabled = true`, stats are downloaded via SFTP before processing
- **Temp Directory**: Specify a custom temp directory for SFTP downloads, or leave empty for system default
- **World Path**: Can use network paths (Windows: `\\server\share`, Linux: `/mnt/share`)

## Database Setup

The application automatically creates all required tables on first run. The database schema includes:

### Tables

- **`players`**: Central player registry with UUID, name, and activity timestamps
- **`player_stats`**: Raw JSON stats for each player
- **`player_stats_*`**: Normalized tables for each stat category (used, mined, broken, etc.)

### Schema Features

- Primary keys on UUIDs
- Foreign key constraints with cascading deletes
- Automatic timestamp tracking
- Indexes on frequently queried columns
- JSON storage for raw stat data

### Optional: Create Database Views

After the first sync, run the provided SQL script to create useful views:

```bash
mysql -u your_user -p your_database < database_views.sql
```

This creates views for:
- Player summaries and activity status
- Leaderboards (top miners, warriors, crafters)
- Death statistics
- Popular items/mobs
- New player tracking

## Usage

### Manual Sync

```bash
# Linux (with virtual environment)
source .venv/bin/activate
python sync_stats.py

# Windows
.venv\Scripts\Activate.ps1
python sync_stats.py
```

### Automated Sync (Linux)

Use the provided runner script with cron:

```bash
# Make the script executable
chmod +x minecraft_stats.sh

# Add to crontab (runs every hour)
crontab -e
# Add this line:
0 * * * * /path/to/minecraft_stats.sh
```

The runner script:
- Activates the virtual environment automatically
- Logs output to `mcstats-sync.log`
- Handles errors gracefully

### Automated Sync (Windows)

Use Task Scheduler:

1. Create a batch file `sync_stats.bat`:
   ```batch
   @echo off
   cd /d "D:\Code Projects\Minecraft Statistics to MySQL"
   call .venv\Scripts\activate.bat
   python sync_stats.py >> sync.log 2>&1
   ```

2. Create a scheduled task to run the batch file periodically

## Database Queries

### Example Queries Using Views

```sql
-- Get active players
SELECT * FROM v_player_summary WHERE activity_status = 'Active';

-- Top 10 miners
SELECT * FROM v_top_miners LIMIT 10;

-- Player comprehensive stats
SELECT * FROM v_player_comprehensive WHERE name = 'PlayerName';

-- Diamond ore leaderboard
SELECT * FROM v_diamond_miners;

-- Most popular blocks mined
SELECT * FROM v_popular_items_mined LIMIT 20;

-- Recent deaths by player
SELECT * FROM v_player_deaths WHERE name = 'PlayerName';
```

### Example Direct Queries

```sql
-- Get all stats for a specific player
SELECT p.name, m.stat_key, m.stat_value
FROM players p
JOIN player_stats_mined m ON p.uuid = m.uuid
WHERE p.name = 'PlayerName'
ORDER BY m.stat_value DESC;

-- Total playtime across all players
SELECT
    p.name,
    c.stat_value / 72000 as hours_played
FROM players p
JOIN player_stats_custom c ON p.uuid = c.uuid
WHERE c.stat_key = 'minecraft:play_time'
ORDER BY hours_played DESC;

-- Most dangerous mob
SELECT stat_key, SUM(stat_value) as total_kills
FROM player_stats_killed
GROUP BY stat_key
ORDER BY total_kills DESC
LIMIT 1;
```

## Project Structure

```
.
├── config.ini              # Configuration file (database, SFTP, paths)
├── sync_stats.py           # Main synchronization script
├── requirements.txt        # Python dependencies
├── database_views.sql      # Optional SQL views for analytics
├── install.sh              # Linux installation script
├── minecraft_stats.sh      # Linux runner script for cron
├── debug_sftp.py           # SFTP connection testing utility
└── README.md               # This file
```

## How It Works

1. **Fetch Stats**:
   - If SFTP is enabled, downloads `usercache.json` and all stat files from remote server to temp directory
   - Otherwise, reads directly from local `world_path`

2. **Parse Stats**:
   - Reads each player's JSON stat file (`UUID.json`)
   - Parses stat sections (mined, killed, crafted, etc.)
   - Maps UUIDs to player names from `usercache.json`

3. **Database Sync**:
   - Creates tables if they don't exist
   - Upserts player information into `players` table
   - Stores raw JSON stats in `player_stats` table
   - Normalizes and upserts individual stats into category-specific tables
   - Removes old stats that no longer exist

4. **Cleanup**:
   - Commits all changes
   - Removes temporary files if SFTP was used

## Troubleshooting

### SFTP Connection Issues

Test your SFTP connection:
```bash
python debug_sftp.py
```

Common issues:
- Verify host, port, username, and password
- Check firewall rules
- Ensure SFTP is enabled on the server
- Verify remote paths exist

### Database Connection Issues

- Verify MySQL is running and accessible
- Check credentials in `config.ini`
- Ensure the database exists (create it manually if needed)
- Verify network connectivity to MySQL server

### Missing Player Names

- Ensure `usercache.json` is accessible
- The file should be in the server root directory (parent of world folder)
- Names may not appear for players who haven't joined since the server started

### Permission Errors

- Ensure the script has read access to the world directory
- Verify write access to the temp directory (if specified)
- Check MySQL user permissions (needs CREATE, INSERT, UPDATE, DELETE)

## Dependencies

- **mysql-connector-python**: MySQL database connectivity
- **paramiko**: SFTP/SSH client for remote file access

## Security Notes

- **Never commit `config.ini`** to version control with real credentials
- Use a dedicated MySQL user with limited permissions
- Consider using SSH key authentication instead of passwords for SFTP
- Restrict database access to localhost if possible
- Use strong passwords for all services

## Performance Tips

- Run sync during off-peak hours to minimize server impact
- Use SFTP mode to avoid direct filesystem access on production servers
- Consider indexing additional columns based on your query patterns
- Archive old player data periodically if the database grows large

## License

This project is provided as-is for personal and educational use.

## Contributing

Contributions are welcome! Please ensure any pull requests:
- Follow existing code style
- Include appropriate error handling
- Update documentation as needed

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review the configuration carefully
3. Test SFTP connectivity with `debug_sftp.py`
4. Check log files for detailed error messages
