"""Tenant-scoped SQLite persistence. Writes use a serialized transaction."""

import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from fastapi import HTTPException

from .creator_models import Activity, License, LicenseInput, Payment, Renewal, User


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> date:
    return datetime.now(timezone.utc).date()


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    path = Path(os.environ.get("RESOLVE_CREATOR_DB", "data/creator.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize() -> None:
    with db() as c:
        c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                salt TEXT NOT NULL, data TEXT NOT NULL, created INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS records_owner ON records(user_id, kind);
            CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, until INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS billing_events (id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS checkout_sessions (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL
            );
        """)
        c.execute("DELETE FROM sessions WHERE expires < ?", (int(time.time()),))
        c.execute("DELETE FROM limits WHERE until < ?", (int(time.time()),))
        c.execute(
            "DELETE FROM users WHERE json_extract(data, '$.demo')=1 AND created < ?",
            (int(time.time()) - 86400,),
        )


def throttle(key: str, maximum: int = 15) -> None:
    digest = hashlib.sha256(key.encode()).hexdigest()
    blocked = False
    with db() as c:
        c.execute("DELETE FROM limits WHERE until < ?", (int(time.time()),))
        row = c.execute("SELECT count FROM limits WHERE key=?", (digest,)).fetchone()
        if row and row["count"] >= maximum:
            blocked = True
        else:
            c.execute(
                "INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1",
                (digest, int(time.time()) + 900),
            )
    if blocked:
        raise HTTPException(429, "Too many attempts. Please try again in 15 minutes.")


def password_hash(password: str, salt: str) -> str:
    return hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
    ).hex()


def create_user(email: str, name: str, password: str, demo: bool = False) -> User:
    user = User(id=uuid4().hex, email=email, name=name, demo=demo)
    salt = secrets.token_hex(16)
    hashed = password_hash(password, salt)
    try:
        with db() as c:
            c.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?)",
                (
                    user.id,
                    email,
                    hashed,
                    salt,
                    user.model_dump_json(),
                    int(time.time()),
                ),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(
            409, "Unable to create this account. Try signing in."
        ) from None
    return user


def authenticate(email: str, password: str) -> User:
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    salt = row["salt"] if row else "00" * 16
    hashed = password_hash(password, salt)
    if not row or not secrets.compare_digest(hashed, row["password"]):
        raise HTTPException(401, "Email or password is incorrect.")
    return User.model_validate_json(row["data"])


def user_by_id(c: sqlite3.Connection, user_id: str) -> User:
    row = c.execute("SELECT data FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(401, "Please sign in again.")
    return User.model_validate_json(row["data"])


def save_user(c: sqlite3.Connection, user: User) -> None:
    c.execute("UPDATE users SET data=? WHERE id=?", (user.model_dump_json(), user.id))


def session(user: User) -> str:
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute(
            "INSERT INTO sessions VALUES (?,?,?)",
            (
                token_hash(token),
                user.id,
                int(time.time()) + (86400 if user.demo else 604800),
            ),
        )
    return token


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_user(token: str) -> User:
    with db() as c:
        row = c.execute(
            "SELECT user_id FROM sessions WHERE hash=? AND expires>?",
            (token_hash(token), int(time.time())),
        ).fetchone()
        if not row:
            raise HTTPException(401, "Please sign in to your workspace.")
        return user_by_id(c, row["user_id"])


def save(
    c: sqlite3.Connection,
    user_id: str,
    record: License | Renewal | Payment | Activity,
    kind: str,
) -> None:
    c.execute(
        "INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data WHERE records.user_id=excluded.user_id",
        (record.id, user_id, kind, record.model_dump_json()),
    )


def get(c: sqlite3.Connection, user_id: str, record_id: str, kind: str) -> str:
    row = c.execute(
        "SELECT data FROM records WHERE id=? AND user_id=? AND kind=?",
        (record_id, user_id, kind),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Record not found.")
    return str(row["data"])


def records(c: sqlite3.Connection, user_id: str, kind: str) -> list[str]:
    return [
        str(r["data"])
        for r in c.execute(
            "SELECT data FROM records WHERE user_id=? AND kind=? ORDER BY rowid DESC",
            (user_id, kind),
        )
    ]


def activity(c: sqlite3.Connection, user_id: str, license_id: str, text: str) -> None:
    save(
        c,
        user_id,
        Activity(id=uuid4().hex, license_id=license_id, text=text, created_at=now()),
        "activity",
    )


def paid(c: sqlite3.Connection, user_id: str, renewal_id: str) -> int:
    return sum(
        p.amount_cents
        for raw in records(c, user_id, "payment")
        if (p := Payment.model_validate_json(raw)).renewal_id == renewal_id
        and not p.reversed
    )


def add_license(c: sqlite3.Connection, user: User, data: LicenseInput) -> License:
    current = [
        License.model_validate_json(raw) for raw in records(c, user.id, "license")
    ]
    limit = 10 if user.demo else (2000 if user.plan == "pro" else 3)
    if not data.archived and sum(not item.archived for item in current) >= limit:
        raise HTTPException(
            402,
            f"Your plan supports {limit} active licenses. Archive a license or upgrade.",
        )
    item = License(id=uuid4().hex, **data.model_dump())
    save(c, user.id, item, "license")
    activity(
        c,
        user.id,
        item.id,
        f"Creator recorded license: {item.starts_on} to {item.expires_on}. Scope: {item.scope}",
    )
    return item


def seed_demo(user: User) -> None:
    examples = [
        (
            "Forma",
            "Morning routine · 3 UGC videos",
            "Meta paid ads · US · brand account",
            6,
            45000,
        ),
        (
            "Fieldwork",
            "Weekend essentials · creator ad",
            "Instagram partnership ads · US",
            -4,
            60000,
        ),
        (
            "Sunday Studio",
            "Desk refresh · product demo",
            "TikTok Spark Ads · US",
            18,
            30000,
        ),
    ]
    with db() as c:
        for brand, title, scope, days, fee in examples:
            add_license(
                c,
                user,
                LicenseInput(
                    brand=brand,
                    title=title,
                    scope=scope,
                    contact_email=f"partnerships@{brand.lower().replace(' ', '')}.example",
                    starts_on=today() - timedelta(days=60),
                    expires_on=today() + timedelta(days=days),
                    renewal_fee_cents=fee,
                    renewal_days=30,
                    notes="Fictional sample. Add your agreed terms and evidence before making a real offer.",
                ),
            )
