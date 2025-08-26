from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.crud.users import get_by_email_or_username
from app.core.security import verify_password

router = APIRouter(prefix="/api", tags=["auth"])

@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    identifier = None
    password = None
    ct = request.headers.get("content-type", "")

    try:
        if ct.startswith("application/json"):
            payload = await request.json()
            identifier = (payload.get("email") or payload.get("username") or "").strip()
            password = (payload.get("password") or "")
        else:
            form = await request.form()
            identifier = (form.get("email") or form.get("username") or "").strip()
            password = (form.get("password") or "")
    except Exception:
        # Fallback: leere Felder erzwingen -> 400 unten
        identifier = identifier or ""
        password = password or ""

    if not identifier or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing credentials")

    user = get_by_email_or_username(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    # Session setzen
    request.session["uid"] = user.id
    request.session["username"] = user.username
    request.session["is_admin"] = bool(getattr(user, "is_admin", False))

    return {"ok": True}

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}
