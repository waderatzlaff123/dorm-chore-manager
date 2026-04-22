import sqlite3
from pathlib import Path

DB_PATH = Path("database.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('RA', 'Resident'))
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
            status TEXT NOT NULL DEFAULT 'Pending'
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
            FOREIGN KEY (chore_id) REFERENCES chores (id) ON DELETE CASCADE,
            FOREIGN KEY (resident_id) REFERENCES users (id),
            FOREIGN KEY (assigned_by) REFERENCES users (id)
        )
    """
    )

    user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if user_count == 0:
        conn.executemany(
            "INSERT INTO users (name, role) VALUES (?, ?)",
            [
                ("Alex RA", "RA"),
                ("Jamie Resident", "Resident"),
                ("Morgan Resident", "Resident"),
                ("Taylor Resident", "Resident"),
            ],
        )

    conn.commit()
    conn.close()