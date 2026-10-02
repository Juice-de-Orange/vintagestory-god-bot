"""Persistent memory about players: relationship, notes, gifts, curses, sessions."""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from bot.config import RANK_FORSAKEN, RANK_CURSED, RANK_NEUTRAL, RANK_FAVORED, RANK_CHOSEN


def get_divine_rank(relationship: int) -> str:
    """Rank key (see texts.RANKS) for a relationship value."""
    if relationship >= RANK_CHOSEN:  return "CHOSEN"
    if relationship >= RANK_FAVORED: return "FAVORED"
    if relationship >= RANK_NEUTRAL: return "NOTICED"
    if relationship >= RANK_CURSED:  return "CURSED"
    if relationship >= RANK_FORSAKEN:return "FORSAKEN"
    return "HATED"


class PlayerMemory:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock   = threading.RLock()
        self._init_database()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_database(self):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS players (
                        name                TEXT PRIMARY KEY,
                        first_seen          TEXT,
                        last_seen           TEXT,
                        last_contact        TEXT,
                        relationship        INTEGER DEFAULT 0,
                        total_interactions  INTEGER DEFAULT 0,
                        divine_rank         TEXT DEFAULT 'NOTICED',
                        session_count       INTEGER DEFAULT 0
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS player_notes (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_name TEXT,
                        note        TEXT,
                        created_at  TEXT,
                        FOREIGN KEY (player_name) REFERENCES players(name)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS gifts_given (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_name TEXT,
                        item        TEXT,
                        amount      INTEGER,
                        given_at    TEXT,
                        reason      TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS curses_blessings (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_name TEXT,
                        type        TEXT,  -- 'curse' or 'blessing'
                        effect      TEXT,
                        issued_at   TEXT,
                        expires_at  TEXT,
                        active      INTEGER DEFAULT 1
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS player_sessions (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        player_name TEXT,
                        joined_at   TEXT,
                        left_at     TEXT
                    )
                """)
                # Add columns that older databases do not have yet
                for col, typedef in [
                    ("last_seen",     "TEXT"),
                    ("divine_rank",   "TEXT DEFAULT 'NOTICED'"),
                    ("session_count", "INTEGER DEFAULT 0"),
                ]:
                    try:
                        conn.execute(f"ALTER TABLE players ADD COLUMN {col} {typedef}")
                    except Exception:
                        pass
                conn.commit()

    def get_or_create_player(self, name: str) -> dict:
        with self._lock:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM players WHERE name = ?", (name,)).fetchone()
                if row:
                    return dict(row)
                now = datetime.now().isoformat()
                conn.execute("""
                    INSERT INTO players (name, first_seen, last_seen, last_contact, relationship,
                                        total_interactions, divine_rank, session_count)
                    VALUES (?, ?, ?, ?, 0, 0, 'NOTICED', 0)
                """, (name, now, now, now))
                conn.commit()
                return {"name": name, "first_seen": now, "last_seen": now,
                        "last_contact": now, "relationship": 0,
                        "total_interactions": 0, "divine_rank": "NOTICED", "session_count": 0}

    def update_relationship(self, name: str, change: int, reason: str = None) -> tuple[str, str]:
        """Change the relationship and return (old_rank, new_rank)."""
        with self._lock:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT relationship, divine_rank FROM players WHERE name=?", (name,)).fetchone()
                if not row:
                    self.get_or_create_player(name)
                    row = conn.execute("SELECT relationship, divine_rank FROM players WHERE name=?", (name,)).fetchone()

                # Derived from the value, not read from the stored column: that
                # column may hold rank names from an older version of the bot.
                old_rank = get_divine_rank(row["relationship"])
                new_rel  = max(-100, min(100, row["relationship"] + change))
                new_rank = get_divine_rank(new_rel)

                conn.execute("""
                    UPDATE players SET relationship=?, divine_rank=?, last_contact=?,
                    total_interactions=total_interactions+1 WHERE name=?
                """, (new_rel, new_rank, datetime.now().isoformat(), name))
                conn.commit()

            if reason:
                self.add_note(name, f"relationship {change:+d}: {reason}")
            return old_rank, new_rank

    def record_join(self, name: str):
        with self._lock:
            with self._get_connection() as conn:
                now = datetime.now().isoformat()
                conn.execute("UPDATE players SET last_seen=?, session_count=session_count+1 WHERE name=?", (now, name))
                conn.execute("INSERT INTO player_sessions (player_name, joined_at) VALUES (?, ?)", (name, now))
                conn.commit()

    def record_leave(self, name: str):
        with self._lock:
            with self._get_connection() as conn:
                now = datetime.now().isoformat()
                conn.execute("UPDATE players SET last_seen=? WHERE name=?", (now, name))
                conn.execute("""
                    UPDATE player_sessions SET left_at=? WHERE player_name=?
                    AND left_at IS NULL ORDER BY id DESC LIMIT 1
                """, (now, name))
                conn.commit()

    def days_since_last_seen(self, name: str) -> float:
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute("SELECT last_seen FROM players WHERE name=?", (name,)).fetchone()
                if not row or not row[0]:
                    return 0.0
                try:
                    last = datetime.fromisoformat(row[0])
                    return (datetime.now() - last).total_seconds() / 86400.0
                except Exception:
                    return 0.0

    def add_note(self, player_name: str, note: str):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("INSERT INTO player_notes (player_name, note, created_at) VALUES (?, ?, ?)",
                             (player_name, note, datetime.now().isoformat()))
                conn.commit()

    def get_notes(self, player_name: str, limit: int = 10) -> list:
        with self._lock:
            with self._get_connection() as conn:
                rows = conn.execute("""
                    SELECT note, created_at FROM player_notes WHERE player_name=?
                    ORDER BY created_at DESC LIMIT ?
                """, (player_name, limit)).fetchall()
                return [{"note": r[0], "created_at": r[1]} for r in rows]

    def record_gift(self, player_name: str, item: str, amount: int, reason: str):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("INSERT INTO gifts_given (player_name, item, amount, given_at, reason) VALUES (?,?,?,?,?)",
                             (player_name, item, amount, datetime.now().isoformat(), reason))
                conn.commit()

    def add_curse_or_blessing(self, player_name: str, kind: str, effect: str, expires_days: float = None):
        with self._lock:
            with self._get_connection() as conn:
                expires = None
                if expires_days:
                    from datetime import timedelta
                    expires = (datetime.now() + timedelta(days=expires_days)).isoformat()
                conn.execute("""
                    INSERT INTO curses_blessings (player_name, type, effect, issued_at, expires_at)
                    VALUES (?,?,?,?,?)
                """, (player_name, kind, effect, datetime.now().isoformat(), expires))
                conn.commit()

    def get_active_effects(self, player_name: str) -> list:
        with self._lock:
            with self._get_connection() as conn:
                now = datetime.now().isoformat()
                rows = conn.execute("""
                    SELECT type, effect FROM curses_blessings
                    WHERE player_name=? AND active=1
                    AND (expires_at IS NULL OR expires_at > ?)
                """, (player_name, now)).fetchall()
                return [{"type": r[0], "effect": r[1]} for r in rows]
