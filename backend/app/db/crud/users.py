from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.models import User

def get_by_email_or_username(db: Session, identifier: str) -> Optional[User]:
    """Holt den User entweder per E-Mail oder Username."""
    return db.query(User).filter(
        or_(User.email == identifier, User.username == identifier)
    ).first()

def create(db: Session, email: str, username: str, password_hash: str, is_admin: bool = False) -> int:
    user = User(email=email, username=username, password_hash=password_hash, is_admin=is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.id
def get_by_login(db: Session, login: str) -> Optional[User]:
    """Backward-Compat: wird vom Auth-Router importiert."""
    return get_by_email_or_username(db, login)
