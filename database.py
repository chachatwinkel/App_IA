import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash


def init_db(
    database_path: str | Path,
    demo_user_password: str,
    demo_technician_password: str,
) -> None:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('usuario', 'tecnico'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL REFERENCES users (id),
                observation TEXT NOT NULL CHECK (length(trim(observation)) > 0),
                category TEXT NOT NULL DEFAULT 'revisar'
                    CHECK (category IN ('hardware', 'software', 'red', 'cuenta', 'revisar')),
                priority TEXT
                    CHECK (priority IS NULL OR priority IN ('baja', 'media', 'alta')),
                summary TEXT,
                status TEXT NOT NULL DEFAULT 'abierta'
                    CHECK (status IN ('abierta', 'en curso', 'resuelta'))
            )
            """
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
            """,
            [
                (
                    "usuario",
                    generate_password_hash(demo_user_password),
                    "usuario",
                ),
                (
                    "tecnico",
                    generate_password_hash(demo_technician_password),
                    "tecnico",
                ),
            ],
        )
