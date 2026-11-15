"""SQLite mỏng. Một kết nối dùng chung + khoá, chỉ gọi từ luồng chính của event loop
(tool chạy ở thread riêng nhưng không đụng DB) nên đủ an toàn cho bản thô."""
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  state TEXT NOT NULL,
  fix_round INTEGER NOT NULL DEFAULT 0,   -- số vòng sửa đã dùng sau FAIL
  asked INTEGER NOT NULL DEFAULT 0,       -- số lần Giám đốc đã hỏi lại (tối đa 1 lượt ở bản này)
  questions TEXT,                         -- câu hỏi đang chờ chủ studio trả lời
  note TEXT,                              -- ghi chú/phản hồi cần đưa cho bước kế tiếp
  error TEXT,                             -- lý do dừng ở trạng thái blocked
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job ON events(job_id, id);
"""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            # Migration nhẹ cho DB tạo từ bản trước: thêm cột blocked_from nếu chưa có.
            cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(jobs)")]
            if "blocked_from" not in cols:
                self.conn.execute("ALTER TABLE jobs ADD COLUMN blocked_from TEXT")
                self.conn.commit()

    def execute(self, sql: str, params=()):
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql: str, params=()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params=()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    @staticmethod
    def now() -> float:
        return time.time()
