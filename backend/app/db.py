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
  fix_round INTEGER NOT NULL DEFAULT 0,   -- số vòng sửa đã dùng sau FAIL (trong một đợt)
  asked INTEGER NOT NULL DEFAULT 0,       -- số lần Giám đốc đã hỏi lại (tối đa 1 lượt)
  questions TEXT,                         -- câu hỏi đang chờ chủ studio trả lời
  note TEXT,                              -- phản hồi/hướng dẫn cần đưa cho bước kế tiếp
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
-- Task do Giám đốc chia trong plan.json; mỗi đợt (round) lập kế hoạch lại có bộ task riêng.
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL, round INTEGER NOT NULL, task_id TEXT NOT NULL, role TEXT NOT NULL,
  title TEXT NOT NULL, depends TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | running | done | failed
  started REAL, ended REAL, report TEXT
);
CREATE INDEX IF NOT EXISTS tasks_job ON tasks(job_id, round);
-- Hội thoại chủ studio <-> Giám đốc (chủ chỉ nói chuyện với Giám đốc).
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL, ts REAL NOT NULL, sender TEXT NOT NULL,   -- owner | director
  text TEXT NOT NULL, files TEXT NOT NULL DEFAULT '[]',
  delivered INTEGER NOT NULL DEFAULT 1                            -- tin của chủ gửi lúc job đang chạy: 0 cho tới khi Giám đốc đọc
);
CREATE INDEX IF NOT EXISTS messages_job ON messages(job_id, id);
-- Mỗi lần commit bắt buộc sau khi agent chạy.
CREATE TABLE IF NOT EXISTS commits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL, ts REAL NOT NULL, repo TEXT NOT NULL,     -- job | workspace
  hash TEXT NOT NULL, message TEXT NOT NULL, files INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS commits_job ON commits(job_id, id);
-- Mỗi lượt gọi model: token và chi phí ước tính (chỉ tính khi có đơn giá; model local/OmniRoute tính 0).
CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL, ts REAL NOT NULL, role TEXT NOT NULL, connection TEXT NOT NULL, model TEXT NOT NULL,
  tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0, priced INTEGER NOT NULL DEFAULT 1   -- priced=0: model trả phí nhưng chưa có đơn giá nên chưa tính tiền
);
CREATE INDEX IF NOT EXISTS usage_job ON usage(job_id, id);
"""

# Cột thêm sau này: DB tạo từ bản trước được nâng cấp tại chỗ.
MIGRATIONS = {
    "jobs": {"blocked_from": "TEXT", "workspace": "TEXT", "base_branch": "TEXT", "round": "INTEGER NOT NULL DEFAULT 0", "qa_repairs": "INTEGER NOT NULL DEFAULT 0",
             "tier": "TEXT NOT NULL DEFAULT 'full'", "budget": "REAL"},
    "events": {"actor": "TEXT"},
}


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            for table, cols in MIGRATIONS.items():
                have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
                for col, ddl in cols.items():
                    if col not in have:
                        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
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
