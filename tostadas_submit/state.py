import sqlite3
from datetime import datetime, timezone


VALID_DATABASES = ("biosample", "sra", "genbank")
VALID_STATUSES = ("pending", "prepared", "submitted", "processing", "succeeded", "error")


class StateDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS samples (
                sample_name     TEXT PRIMARY KEY,
                batch_id        TEXT,
                biosample_status TEXT DEFAULT 'pending',
                biosample_acc   TEXT,
                sra_status      TEXT DEFAULT 'pending',
                sra_acc         TEXT,
                genbank_status  TEXT DEFAULT 'pending',
                genbank_acc     TEXT,
                last_updated    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message   TEXT
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                database        TEXT NOT NULL,
                batch_id        TEXT NOT NULL,
                submitted_at    TIMESTAMP,
                status          TEXT DEFAULT 'pending',
                remote_dir      TEXT,
                report_xml      TEXT
            );
        """)
        self.conn.commit()

    def register_samples(self, sample_names, batch_id):
        now = datetime.now(timezone.utc).isoformat()
        for name in sample_names:
            self.conn.execute(
                "INSERT OR IGNORE INTO samples (sample_name, batch_id, last_updated) VALUES (?, ?, ?)",
                (name, batch_id, now),
            )
        self.conn.commit()

    def get_sample(self, sample_name):
        row = self.conn.execute(
            "SELECT * FROM samples WHERE sample_name = ?", (sample_name,)
        ).fetchone()
        return dict(row) if row else None

    def get_samples(self, batch_id=None, database=None, status=None):
        query = "SELECT * FROM samples WHERE 1=1"
        params = []
        if batch_id:
            query += " AND batch_id = ?"
            params.append(batch_id)
        if database and status:
            col = f"{database}_status"
            query += f" AND {col} = ?"
            params.append(status)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_pending_samples(self, database):
        return self.get_samples(database=database, status="pending")

    def update_sample_status(self, sample_name, database, status, accession=None, error=None):
        if database not in VALID_DATABASES:
            raise ValueError(f"Invalid database: {database}")
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        now = datetime.now(timezone.utc).isoformat()
        status_col = f"{database}_status"
        acc_col = f"{database}_acc"
        self.conn.execute(
            f"UPDATE samples SET {status_col} = ?, {acc_col} = COALESCE(?, {acc_col}), "
            f"error_message = COALESCE(?, error_message), last_updated = ? "
            f"WHERE sample_name = ?",
            (status, accession, error, now, sample_name),
        )
        self.conn.commit()

    def record_submission(self, database, batch_id, remote_dir=None):
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            "INSERT INTO submissions (database, batch_id, submitted_at, status, remote_dir) "
            "VALUES (?, ?, ?, 'submitted', ?)",
            (database, batch_id, now, remote_dir),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_submission(self, submission_id, status=None, report_xml=None):
        updates = []
        params = []
        if status:
            updates.append("status = ?")
            params.append(status)
        if report_xml:
            updates.append("report_xml = ?")
            params.append(report_xml)
        if not updates:
            return
        params.append(submission_id)
        self.conn.execute(
            f"UPDATE submissions SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        self.conn.commit()

    def get_submissions(self, database=None, status=None):
        query = "SELECT * FROM submissions WHERE 1=1"
        params = []
        if database:
            query += " AND database = ?"
            params.append(database)
        if status:
            query += " AND status = ?"
            params.append(status)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_all_samples(self):
        rows = self.conn.execute("SELECT * FROM samples ORDER BY sample_name").fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
