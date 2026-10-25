"""The app the agents work on. Deliberately trivial: the point is the policy."""

import sqlite3


def add(db: sqlite3.Connection, body: str) -> int:
    return db.execute("INSERT INTO notes (body) VALUES (?)", (body,)).lastrowid


def list_all(db):
    return [r[0] for r in db.execute("SELECT body FROM notes ORDER BY id")]
