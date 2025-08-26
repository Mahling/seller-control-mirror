from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from app.db.models import User

def get_by_login(db: Session, login: str) -> Optional[User]:
    stmt = select(User).where(or_(User.email == login, User.username == login)).limit(1)
    return db.execute(stmt).scalar_one_or_none()

def create(db: Session, email: str, username: str, password_hash: str, is_admin: bool=False) -> int:
    u = User(email=email, username=username, password_hash=password_hash, is_admin=is_admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u.id
