"""The app the agents work on. Deliberately trivial: the point is the policy."""

import sqlite3


def add(db: sqlite3.Connection, body: str) -> int:
    return db.execute("INSERT INTO notes (body) VALUES (?)", (body,)).lastrowid
