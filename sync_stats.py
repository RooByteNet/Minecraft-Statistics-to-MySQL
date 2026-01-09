import configparser
import json
import pathlib
import shutil
import sys
import tempfile
from typing import Callable, Dict, Optional, Tuple

import mysql.connector
import paramiko
from mysql.connector.connection import MySQLConnection


def load_config(path: pathlib.Path) -> dict:
    config = configparser.ConfigParser()
    if not config.read(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        world_path = pathlib.Path(config["paths"]["world_path"]).expanduser()
        temp_dir = config["paths"].get("temp_dir", "").strip()
        temp_dir_path = pathlib.Path(temp_dir).expanduser() if temp_dir else None
        mysql_section = config["mysql"]
    except KeyError as exc:
        raise KeyError(f"Missing config key: {exc}") from exc

    stats_dir = world_path / "stats"
    usercache_path = world_path.parent / "usercache.json"

    return {
        "world_path": world_path,
        "stats_dir": stats_dir,
        "usercache_path": usercache_path,
        "temp_dir": temp_dir_path,
        "mysql": {
            "host": mysql_section.get("host", "localhost"),
            "port": mysql_section.getint("port", 3306),
            "user": mysql_section.get("user"),
            "password": mysql_section.get("password"),
            "database": mysql_section.get("database"),
            "table": mysql_section.get("table", "player_stats"),
            "used_table": mysql_section.get("used_table", "player_stats_used"),
            "mined_table": mysql_section.get("mined_table", "player_stats_mined"),
            "broken_table": mysql_section.get("broken_table", "player_stats_broken"),
            "custom_table": mysql_section.get("custom_table", "player_stats_custom"),
            "killed_table": mysql_section.get("killed_table", "player_stats_killed"),
            "crafted_table": mysql_section.get("crafted_table", "player_stats_crafted"),
            "dropped_table": mysql_section.get("dropped_table", "player_stats_dropped"),
            "killed_by_table": mysql_section.get("killed_by_table", "player_stats_killed_by"),
            "picked_up_table": mysql_section.get("picked_up_table", "player_stats_picked_up"),
        },
        "sftp": {
            "enabled": config.getboolean("sftp", "enabled", fallback=False),
            "host": config.get("sftp", "host", fallback=""),
            "port": config.getint("sftp", "port", fallback=22),
            "user": config.get("sftp", "user", fallback=""),
            "password": config.get("sftp", "password", fallback=""),
            "remote_root_path": config.get("sftp", "remote_root_path", fallback=""),
            "world_name": config.get("sftp", "world_name", fallback=""),
            "remote_world_path": config.get("sftp", "remote_world_path", fallback=""),
        },
    }


def log(msg: str) -> None:
    print(f"[sync] {msg}")


def load_usercache(path: pathlib.Path) -> Dict[str, str]:
    """Load usercache.json and return UUID -> name mapping."""
    if not path.exists():
        log(f"Usercache not found at {path}; names will not be populated")
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            entries = json.load(f)

        uuid_to_name = {}
        for entry in entries:
            if "uuid" in entry and "name" in entry:
                uuid_to_name[entry["uuid"]] = entry["name"]

        log(f"Loaded {len(uuid_to_name)} player names from usercache")
        return uuid_to_name
    except (json.JSONDecodeError, OSError) as e:
        log(f"Failed to load usercache: {e}")
        return {}


def ensure_column(conn: MySQLConnection, schema: str, table: str, column: str, definition: str) -> None:
    check_sql = """
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND column_name = %s
    """
    with conn.cursor() as cur:
        cur.execute(check_sql, (schema, table, column))
        exists = cur.fetchone()[0] > 0
        if not exists:
            cur.execute(f"ALTER TABLE `{table}` ADD COLUMN {definition}")


def ensure_players_table(conn: MySQLConnection, schema: str) -> None:
    """Create a central players table with proper primary key."""
    create_sql = """
    CREATE TABLE IF NOT EXISTS `players` (
        uuid CHAR(36) PRIMARY KEY,
        name VARCHAR(32),
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
    ensure_column(conn, schema, "players", "first_seen", "first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ensure_column(conn, schema, "players", "last_seen", "last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    conn.commit()


def ensure_raw_table(conn: MySQLConnection, schema: str, table: str) -> None:
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS `{table}` (
        uuid CHAR(36) PRIMARY KEY,
        stats_json JSON,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_{table}_player FOREIGN KEY (uuid)
            REFERENCES players(uuid)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
    ensure_column(conn, schema, table, "stats_json", "stats_json JSON")
    ensure_column(conn, schema, table, "updated_at", "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    conn.commit()


def ensure_section_table(conn: MySQLConnection, schema: str, table: str) -> None:
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS `{table}` (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        uuid CHAR(36) NOT NULL,
        stat_key VARCHAR(96) NOT NULL,
        stat_value BIGINT UNSIGNED,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uk_uuid_stat (uuid, stat_key),
        INDEX idx_stat_key (stat_key),
        INDEX idx_stat_value (stat_value),
        CONSTRAINT fk_{table}_player FOREIGN KEY (uuid)
            REFERENCES players(uuid)
            ON DELETE CASCADE
            ON UPDATE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
    ensure_column(conn, schema, table, "stat_key", "stat_key VARCHAR(96) NOT NULL")
    ensure_column(conn, schema, table, "stat_value", "stat_value BIGINT UNSIGNED")
    ensure_column(conn, schema, table, "updated_at", "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    conn.commit()


def maybe_fetch_world_via_sftp(sftp_cfg: dict, temp_dir: Optional[pathlib.Path]) -> Tuple[Optional[pathlib.Path], Optional[Callable[[], None]]]:
    if not sftp_cfg.get("enabled"):
        return None, None
    host = sftp_cfg.get("host")
    remote_world = sftp_cfg.get("remote_world_path")
    remote_root = sftp_cfg.get("remote_root_path", "")
    world_name = sftp_cfg.get("world_name", "")

    if world_name and remote_root:
        remote_world = f"{remote_root.rstrip('/')}/{world_name.strip('/')}"

    if not host or not remote_world:
        return None, None

    port = sftp_cfg.get("port", 22)
    user = sftp_cfg.get("user")
    password = sftp_cfg.get("password")

    mkdtemp_dir = str(temp_dir) if temp_dir else None
    temp_root = pathlib.Path(tempfile.mkdtemp(prefix="mcstats_sftp_", dir=mkdtemp_dir))
    local_world = temp_root / "world"
    local_world.mkdir(parents=True, exist_ok=True)

    log(f"SFTP fetch enabled; connecting to {host}:{port}")
    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            # Download usercache.json from root
            remote_usercache = f"{remote_root.rstrip('/')}/usercache.json" if remote_root else None
            if remote_usercache:
                try:
                    local_usercache = temp_root / "usercache.json"
                    sftp.get(remote_usercache, str(local_usercache))
                    log("Downloaded usercache.json")
                except IOError:
                    log("usercache.json not found on remote")

            # Download stats files
            remote_stats = f"{remote_world.rstrip('/')}/stats"
            local_stats = local_world / "stats"
            local_stats.mkdir(parents=True, exist_ok=True)

            entries = sftp.listdir(remote_stats)
            log(f"Found {len(entries)} stat files on remote; downloading")
            for entry in entries:
                if entry.endswith(".json"):
                    sftp.get(f"{remote_stats}/{entry}", str(local_stats / entry))
        finally:
            sftp.close()
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    finally:
        transport.close()

    def cleanup() -> None:
        shutil.rmtree(temp_root, ignore_errors=True)

    return local_world, cleanup


SECTION_KEYS = [
    "minecraft:used",
    "minecraft:mined",
    "minecraft:broken",
    "minecraft:custom",
    "minecraft:killed",
    "minecraft:crafted",
    "minecraft:dropped",
    "minecraft:killed_by",
    "minecraft:picked_up",
]


def parse_stats(path: pathlib.Path) -> Optional[Tuple[Dict[str, Dict[str, int]], dict]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    stats_section = data.get("stats", {})
    sections: Dict[str, Dict[str, int]] = {}

    for section in SECTION_KEYS:
        raw_vals = stats_section.get(section, {})
        if not isinstance(raw_vals, dict):
            continue
        cleaned = {}
        for key, val in raw_vals.items():
            try:
                cleaned[key] = int(val)
            except (TypeError, ValueError):
                continue
        if cleaned:
            sections[section] = cleaned

    return sections, data


def upsert_player(conn: MySQLConnection, uuid: str, name: Optional[str]) -> None:
    """Upsert player into the central players table."""
    sql = """
    INSERT INTO `players` (uuid, name, first_seen, last_seen)
    VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON DUPLICATE KEY UPDATE
        name = COALESCE(VALUES(name), name),
        last_seen = CURRENT_TIMESTAMP;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (uuid, name))


def upsert_raw(conn: MySQLConnection, table: str, uuid: str, raw_stats: dict) -> None:
    sql = f"""
    INSERT INTO `{table}` (uuid, stats_json)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
        stats_json = VALUES(stats_json),
        updated_at = CURRENT_TIMESTAMP;
    """
    args = (uuid, json.dumps(raw_stats))
    with conn.cursor() as cur:
        cur.execute(sql, args)


def upsert_section(conn: MySQLConnection, table: str, uuid: str, stats: Dict[str, int]) -> None:
    # Delete old stats for this player that are no longer present
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM `{table}` WHERE uuid = %s", (uuid,))

    if not stats:
        return

    sql = f"""
    INSERT INTO `{table}` (uuid, stat_key, stat_value)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE
        stat_value = VALUES(stat_value),
        updated_at = CURRENT_TIMESTAMP;
    """

    rows = [(uuid, key, val) for key, val in stats.items()]

    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def sync(config_path: pathlib.Path) -> None:
    cfg = load_config(config_path)
    mysql_cfg = cfg["mysql"]
    sftp_cfg = cfg.get("sftp", {})
    temp_dir = cfg.get("temp_dir")

    log("Starting sync")

    stats_dir = cfg["stats_dir"]
    usercache_path = cfg["usercache_path"]
    cleanup_fn: Optional[Callable[[], None]] = None

    try:
        if temp_dir:
            temp_dir.mkdir(parents=True, exist_ok=True)
        fetched_world, cleanup = maybe_fetch_world_via_sftp(sftp_cfg, temp_dir)
        if fetched_world:
            stats_dir = fetched_world / "stats"
            usercache_path = fetched_world.parent / "usercache.json"
            cleanup_fn = cleanup
            log(f"Using downloaded world at {stats_dir}")
        else:
            log(f"Using local world path {stats_dir}")
    except Exception:
        # If remote fetch fails, ensure cleanup of temp dir then re-raise
        if cleanup_fn:
            cleanup_fn()
        raise

    if not stats_dir.exists():
        raise FileNotFoundError(f"Stats directory not found: {stats_dir}")

    # Load player names from usercache
    uuid_to_name = load_usercache(usercache_path)

    log("Connecting to MySQL")
    conn = mysql.connector.connect(
        host=mysql_cfg["host"],
        port=mysql_cfg["port"],
        user=mysql_cfg["user"],
        password=mysql_cfg["password"],
        database=mysql_cfg["database"],
        autocommit=False,
    )

    try:
        db_schema = mysql_cfg["database"]
        
        log("Ensuring players table")
        ensure_players_table(conn, db_schema)
        
        log("Ensuring raw stats table")
        ensure_raw_table(conn, db_schema, mysql_cfg["table"])

        section_table_map = {
            "minecraft:used": mysql_cfg["used_table"],
            "minecraft:mined": mysql_cfg["mined_table"],
            "minecraft:broken": mysql_cfg["broken_table"],
            "minecraft:custom": mysql_cfg["custom_table"],
            "minecraft:killed": mysql_cfg["killed_table"],
            "minecraft:crafted": mysql_cfg["crafted_table"],
            "minecraft:dropped": mysql_cfg["dropped_table"],
            "minecraft:killed_by": mysql_cfg["killed_by_table"],
            "minecraft:picked_up": mysql_cfg["picked_up_table"],
        }

        for table in section_table_map.values():
            log(f"Ensuring table {table}")
            ensure_section_table(conn, db_schema, table)

        processed = 0
        for stats_file in stats_dir.glob("*.json"):
            uuid = stats_file.stem
            parsed = parse_stats(stats_file)
            if parsed is None:
                continue
            sections, raw_stats = parsed
            player_name = uuid_to_name.get(uuid)
            
            # Upsert player first (required for foreign keys)
            upsert_player(conn, uuid, player_name)
            upsert_raw(conn, mysql_cfg["table"], uuid, raw_stats)

            for section_key, stats_dict in sections.items():
                table = section_table_map.get(section_key)
                if not table:
                    continue
                upsert_section(conn, table, uuid, stats_dict)

            processed += 1
            if processed % 50 == 0:
                log(f"Processed {processed} player stat files...")

        conn.commit()
        log(f"Sync complete. Players processed: {processed}")
    finally:
        conn.close()
        if cleanup_fn:
            cleanup_fn()
            log("Cleaned up temporary download")


def main() -> None:
    config_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("config.ini")
    sync(config_path)
    print("Sync complete.")


if __name__ == "__main__":
    main()
