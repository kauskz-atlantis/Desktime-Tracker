import sqlite3
import json

DEFAULT_FILE_NAME = "tracker.db"

class Database:
    def __init__(self, file_name:str = DEFAULT_FILE_NAME):
        self.conn = sqlite3.connect(file_name, timeout=10, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT
            );
        """)
        self.conn.commit()
    
    def save_log(self, record):
        self.cursor.execute("INSERT INTO logs(data) VALUES (?)", (json.dumps(record),))
        self.conn.commit()
    
    def fetch_logs(self):
        self.cursor.execute("SELECT id, data FROM logs ORDER BY id ASC LIMIT 50")
        rows = self.cursor.fetchall()
        return rows
    
    def delete_logs(self, ids:list):
        args = ','.join(['?'] * len(ids))
        self.cursor.execute(f"DELETE FROM LOGS WHERE id IN ({args})", (*ids,))
        self.conn.commit()
    
    def close(self):
        self.conn.close()