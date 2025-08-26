from typing import Generator, Optional
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user_id(request: Request) -> Optional[int]:
    return request.session.get("uid")

def require_auth(request: Request):
    if not request.session.get("uid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
