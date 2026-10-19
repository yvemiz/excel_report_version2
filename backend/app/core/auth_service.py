"""Persistent accounts and revocable cookie sessions for private workspaces."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from cryptography.fernet import Fernet

COOKIE_NAME = "excel_report_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
PASSWORD_ROUNDS = 600_000


class AuthStore:
    def __init__(self, data_dir: str):
        root = Path(data_dir)
        root.mkdir(parents=True, exist_ok=True)
        self.db_path = str(root / "accounts.db")
        key_path = root / "auth.key"
        try:
            with key_path.open("xb") as file:
                file.write(Fernet.generate_key())
            os.chmod(key_path, 0o600)
        except FileExistsError:
            pass
        self.cipher = Fernet(key_path.read_bytes())
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_attempts (
                    identity TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    attempted_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_auth_attempts
                    ON auth_attempts(identity, kind, attempted_at);
                CREATE TABLE IF NOT EXISTS model_configs (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    encrypted_key TEXT NOT NULL DEFAULT '',
                    base_url TEXT NOT NULL,
                    model TEXT NOT NULL,
                    agent_mode TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS school_profiles (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    school_name TEXT NOT NULL DEFAULT '',
                    school_code TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    academic_year TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL DEFAULT 'real',
                    storage_key TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    current_revision INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_datasets_user
                    ON datasets(user_id, status, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_datasets_one_default
                    ON datasets(user_id) WHERE is_default = 1;
                CREATE TABLE IF NOT EXISTS report_versions (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                    revision_no INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    school_name TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    agent_mode TEXT NOT NULL DEFAULT '',
                    checkpoint_dir TEXT NOT NULL,
                    export_dir TEXT NOT NULL,
                    chart_dir TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    completed_at INTEGER,
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_report_versions_dataset
                    ON report_versions(dataset_id, created_at DESC);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def hash_password(password: str, salt: str = "") -> str:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_ROUNDS
        ).hex()
        return f"pbkdf2_sha256${PASSWORD_ROUNDS}${salt}${digest}"

    @classmethod
    def verify_password(cls, password: str, encoded: str) -> bool:
        try:
            algorithm, rounds, salt, expected = encoded.split("$")
            if algorithm != "pbkdf2_sha256" or int(rounds) != PASSWORD_ROUNDS:
                return False
            return hmac.compare_digest(cls.hash_password(password, salt).split("$")[-1], expected)
        except (ValueError, TypeError):
            return False

    def allow_attempt(self, identity: str, kind: str) -> bool:
        now = int(time.time())
        window, limit = (3600, 5) if kind == "register" else (900, 10)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM auth_attempts WHERE attempted_at < ?", (now - 3600,))
            count = conn.execute(
                "SELECT COUNT(*) FROM auth_attempts "
                "WHERE identity=? AND kind=? AND attempted_at>?",
                (identity, kind, now - window),
            ).fetchone()[0]
            if count >= limit:
                return False
            conn.execute("INSERT INTO auth_attempts VALUES(?,?,?)", (identity, kind, now))
            return True

    def register(self, username: str, display_name: str, password: str):
        encoded = self.hash_password(password)
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users(username,display_name,password_hash,created_at) VALUES(?,?,?,?)",
                (username.lower(), display_name or username, encoded, int(time.time())),
            )
            return {
                "id": cursor.lastrowid,
                "username": username.lower(),
                "display_name": display_name or username,
            }

    def login(self, username: str, password: str):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username.lower(),)).fetchone()
        # Unknown accounts take the same password hashing path.
        encoded = row["password_hash"] if row else f"pbkdf2_sha256${PASSWORD_ROUNDS}${'0' * 32}${'0' * 64}"
        valid = self.verify_password(password, encoded)
        if not row or not valid:
            return None
        return {key: row[key] for key in ("id", "username", "display_name")}

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            conn.execute(
                "INSERT INTO sessions VALUES(?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), user_id, now + SESSION_SECONDS),
            )
        return token

    def get_user(self, token: str):
        if not token or len(token) > 128:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT u.id,u.username,u.display_name FROM sessions s "
                "JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time())),
            ).fetchone()
            return dict(row) if row else None

    def revoke_session(self, token: str):
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )

    def load_config(self, user_id: int):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM model_configs WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return {
                "api_key": "", "base_url": "https://api.deepseek.com",
                "model": "deepseek-chat", "agent_mode": "pi_agent",
            }
        return {
            "api_key": self.cipher.decrypt(row["encrypted_key"].encode()).decode() if row["encrypted_key"] else "",
            "base_url": row["base_url"], "model": row["model"], "agent_mode": row["agent_mode"],
        }

    def save_config(self, user_id: int, config: dict):
        encrypted = self.cipher.encrypt(config["api_key"].encode()).decode() if config["api_key"] else ""
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO model_configs VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                "encrypted_key=excluded.encrypted_key,base_url=excluded.base_url,"
                "model=excluded.model,agent_mode=excluded.agent_mode",
                (user_id, encrypted, config["base_url"], config["model"], config["agent_mode"]),
            )


    # ---- Single-school instance, datasets and report versions -----------------

    def get_school_profile(self, user_id: int):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT school_name, school_code FROM school_profiles WHERE user_id=?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else {"school_name": "", "school_code": ""}

    def save_school_profile(self, user_id: int, school_name: str, school_code: str = ""):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO school_profiles(user_id,school_name,school_code,updated_at) "
                "VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                "school_name=excluded.school_name,school_code=excluded.school_code,"
                "updated_at=excluded.updated_at",
                (user_id, school_name.strip(), school_code.strip(), int(time.time())),
            )
        return self.get_school_profile(user_id)

    def list_datasets(self, user_id: int, include_archived: bool = False):
        sql = "SELECT * FROM datasets WHERE user_id=?"
        params = [user_id]
        if not include_archived:
            sql += " AND status='active'"
        sql += " ORDER BY is_default DESC, created_at DESC"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def get_dataset(self, user_id: int, dataset_id: str):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE id=? AND user_id=?",
                (dataset_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def get_default_dataset(self, user_id: int):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE user_id=? AND status='active' "
                "ORDER BY is_default DESC, created_at ASC LIMIT 1",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_dataset(
        self,
        user_id: int,
        name: str,
        academic_year: str = "",
        kind: str = "real",
        storage_key: str = "",
        is_default: bool = False,
    ):
        dataset_id = f"ds_{uuid.uuid4().hex}"
        storage_key = storage_key or f"datasets/{dataset_id}"
        now = int(time.time())
        with self.connect() as conn:
            if is_default:
                conn.execute("UPDATE datasets SET is_default=0 WHERE user_id=?", (user_id,))
            conn.execute(
                "INSERT INTO datasets(id,user_id,name,academic_year,kind,storage_key,"
                "is_default,current_revision,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,1,'active',?,?)",
                (dataset_id, user_id, name.strip(), academic_year.strip(), kind,
                 storage_key, 1 if is_default else 0, now, now),
            )
            if not is_default and not conn.execute(
                "SELECT 1 FROM datasets WHERE user_id=? AND is_default=1", (user_id,)
            ).fetchone():
                conn.execute("UPDATE datasets SET is_default=1 WHERE id=?", (dataset_id,))
        return self.get_dataset(user_id, dataset_id)

    def update_dataset(self, user_id: int, dataset_id: str, **fields):
        allowed = {"name", "academic_year", "status"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_dataset(user_id, dataset_id)
        assignments = ", ".join(f"{key}=?" for key in updates)
        values = list(updates.values()) + [int(time.time()), dataset_id, user_id]
        with self.connect() as conn:
            conn.execute(
                f"UPDATE datasets SET {assignments}, updated_at=? WHERE id=? AND user_id=?",
                values,
            )
        return self.get_dataset(user_id, dataset_id)

    def set_default_dataset(self, user_id: int, dataset_id: str):
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM datasets WHERE id=? AND user_id=? AND status='active'",
                (dataset_id, user_id),
            ).fetchone()
            if not exists:
                return None
            conn.execute("UPDATE datasets SET is_default=0 WHERE user_id=?", (user_id,))
            conn.execute(
                "UPDATE datasets SET is_default=1, updated_at=? WHERE id=?",
                (int(time.time()), dataset_id),
            )
        return self.get_dataset(user_id, dataset_id)

    def increment_dataset_revision(self, user_id: int, dataset_id: str):
        with self.connect() as conn:
            conn.execute(
                "UPDATE datasets SET current_revision=current_revision+1, updated_at=? "
                "WHERE id=? AND user_id=?",
                (int(time.time()), dataset_id, user_id),
            )
            row = conn.execute(
                "SELECT current_revision FROM datasets WHERE id=? AND user_id=?",
                (dataset_id, user_id),
            ).fetchone()
        return int(row["current_revision"]) if row else 0

    def create_report_version(
        self,
        dataset_id: str,
        revision_no: int,
        checkpoint_dir: str,
        export_dir: str,
        chart_dir: str = "",
        school_name: str = "",
        model: str = "",
        agent_mode: str = "",
        status: str = "running",
        report_version_id: str = "",
    ):
        report_id = report_version_id or f"rv_{uuid.uuid4().hex}"
        now = int(time.time())
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO report_versions(id,dataset_id,revision_no,status,school_name,"
                "model,agent_mode,checkpoint_dir,export_dir,chart_dir,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (report_id, dataset_id, revision_no, status, school_name.strip(),
                 model, agent_mode, checkpoint_dir, export_dir, chart_dir, now),
            )
        return self.get_report_version(report_id)

    def list_report_versions(self, dataset_id: str):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM report_versions WHERE dataset_id=? "
                "ORDER BY created_at DESC, revision_no DESC",
                (dataset_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_report_version(self, report_version_id: str):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM report_versions WHERE id=?",
                (report_version_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_report_version(self, report_version_id: str, **fields):
        allowed = {"status", "completed_at", "error", "school_name", "model", "agent_mode"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_report_version(report_version_id)
        assignments = ", ".join(f"{key}=?" for key in updates)
        values = list(updates.values()) + [report_version_id]
        with self.connect() as conn:
            conn.execute(
                f"UPDATE report_versions SET {assignments} WHERE id=?",
                values,
            )
        return self.get_report_version(report_version_id)
