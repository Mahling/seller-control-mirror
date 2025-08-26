from typing import Optional, Mapping
from sqlalchemy import text
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.verify(password, password_hash)
    except Exception:
        return False

def ensure_users_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS sc_users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """))
    db.commit()

def find_user(db: Session, login: str) -> Optional[Mapping]:
    row = db.execute(
        text("""SELECT id, email, username, password_hash, is_active
                FROM sc_users
                WHERE email=:l OR username=:l
                LIMIT 1"""),
        {"l": login},
    ).mappings().first()
    return row

def create_user(db: Session, email: str, username: str, password: str) -> int:
    ph = hash_password(password)
    row = db.execute(
        text("""INSERT INTO sc_users(email, username, password_hash)
                VALUES (:e, :u, :p)
                ON CONFLICT DO NOTHING
                RETURNING id"""),
        {"e": email, "u": username, "p": ph},
    ).first()
    if row is None:
        # User existiert schon – ID zurückgeben
        row2 = db.execute(
            text("SELECT id FROM sc_users WHERE email=:e OR username=:u"),
            {"e": email, "u": username},
        ).first()
        db.commit()
        return int(row2[0])
    db.commit()
    return int(row[0])
