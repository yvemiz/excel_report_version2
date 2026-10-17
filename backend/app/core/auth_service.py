"""Persistent accounts and revocable cookie sessions for private workspaces."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
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
