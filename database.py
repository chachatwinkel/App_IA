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
