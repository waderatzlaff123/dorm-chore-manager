import sqlite3
from pathlib import Path

DB_PATH = Path("database.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn, table_name, column_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def init_db():
    conn = get_db_connection()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_name TEXT NOT NULL,
            room_code TEXT NOT NULL UNIQUE,
            created_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT,
            role TEXT NOT NULL CHECK (role IN ('RA', 'Resident')),
            room_id INTEGER,
            FOREIGN KEY (room_id) REFERENCES rooms (id)
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            room_id INTEGER,
            created_by INTEGER,
            FOREIGN KEY (room_id) REFERENCES rooms (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chore_id INTEGER NOT NULL,
            resident_id INTEGER NOT NULL,
            assigned_by INTEGER NOT NULL,
            room_id INTEGER,
            FOREIGN KEY (chore_id) REFERENCES chores (id) ON DELETE CASCADE,
            FOREIGN KEY (resident_id) REFERENCES users (id),
            FOREIGN KEY (assigned_by) REFERENCES users (id),
            FOREIGN KEY (room_id) REFERENCES rooms (id)
        )
    """
    )

    if not _column_exists(conn, "users", "email"):
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if not _column_exists(conn, "users", "password_hash"):
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if not _column_exists(conn, "users", "room_id"):
        conn.execute("ALTER TABLE users ADD COLUMN room_id INTEGER")

    if not _column_exists(conn, "chores", "room_id"):
        conn.execute("ALTER TABLE chores ADD COLUMN room_id INTEGER")
    if not _column_exists(conn, "chores", "created_by"):
        conn.execute("ALTER TABLE chores ADD COLUMN created_by INTEGER")

    if not _column_exists(conn, "assignments", "room_id"):
        conn.execute("ALTER TABLE assignments ADD COLUMN room_id INTEGER")

    room_count = conn.execute("SELECT COUNT(*) AS count FROM rooms").fetchone()["count"]
    if room_count == 0:
        conn.execute(
            "INSERT INTO rooms (room_name, room_code, created_by) VALUES (?, ?, ?)",
            ("DormTasker Default", "DEMO2026", None),
        )

    default_room_id = conn.execute(
        "SELECT id FROM rooms ORDER BY id LIMIT 1"
    ).fetchone()["id"]

    user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if user_count == 0:
        conn.executemany(
            "INSERT INTO users (name, email, password_hash, role, room_id) VALUES (?, ?, ?, ?, ?)",
            [
                ("Alex RA", "alex@dormtasker.app", None, "RA", default_room_id),
                (
                    "Jamie Resident",
                    "jamie@dormtasker.app",
                    None,
                    "Resident",
                    default_room_id,
                ),
                (
                    "Morgan Resident",
                    "morgan@dormtasker.app",
                    None,
                    "Resident",
                    default_room_id,
                ),
                (
                    "Taylor Resident",
                    "taylor@dormtasker.app",
                    None,
                    "Resident",
                    default_room_id,
                ),
            ],
        )

    conn.execute("UPDATE users SET room_id = ? WHERE room_id IS NULL", (default_room_id,))
    conn.execute("UPDATE chores SET room_id = ? WHERE room_id IS NULL", (default_room_id,))
    conn.execute(
        """
        UPDATE assignments
        SET room_id = ?
        WHERE room_id IS NULL
        """,
        (default_room_id,),
    )

    conn.commit()
    conn.close()