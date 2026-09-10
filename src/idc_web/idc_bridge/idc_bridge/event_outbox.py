"""Durable ROS-event queue. Only MQTT PUBACK removes a pending event.

All database access runs on the ROS executor thread, never the MQTT thread.
Delivery is at least once: consumers must deduplicate a replay after a crash.
"""
import json
from pathlib import Path
import sqlite3


class EventOutbox:
    def __init__(self, path):
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute(
            'CREATE TABLE IF NOT EXISTS pending_events '
            '(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)'
        )
        self.db.commit()

    def enqueue(self, payload):
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        with self.db:
            self.db.execute('INSERT INTO pending_events(payload) VALUES (?)', (encoded,))

    def peek(self):
        return self.db.execute(
            'SELECT id, payload FROM pending_events ORDER BY id LIMIT 1'
        ).fetchone()

    def acknowledge(self, row_id):
        with self.db:
            self.db.execute('DELETE FROM pending_events WHERE id = ?', (row_id,))

    def close(self):
        self.db.close()
