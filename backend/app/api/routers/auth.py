from fastapi import APIRouter, Depends, Request, HTTPException
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.crud.users import get_by_email_or_username
from app.core.security import verify_password

router = APIRouter(prefix="/api", tags=["auth"])

@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    """
    Akzeptiert:
      - Content-Type: application/json  -> {"identifier": "...", "password": "..."}
      - Content-Type: application/x-www-form-urlencoded (oder multipart/form-data)
        -> Felder: identifier ODER email ODER username, und password
    """
    identifier = None
    password = None

    ctype = request.headers.get("content-type", "")
    try:
        if ctype.startswith("application/json"):
            data = await request.json()
            identifier = (data.get("identifier") or data.get("email") or data.get("username") or "").strip()
            password = data.get("password") or ""
        else:
            form = await request.form()
            identifier = (form.get("identifier") or form.get("email") or form.get("username") or "").strip()
            password = form.get("password") or ""
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    if not identifier or not password:
        raise HTTPException(status_code=400, detail="Missing credentials")

    user = get_by_email_or_username(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        # Fail-safe: Session leeren
        request.session.pop("uid", None)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # OK -> Session setzen
    request.session["uid"] = user.id
    return JSONResponse({"ok": True})

@router.post("/logout")
async def logout(request: Request):
    request.session.pop("uid", None)
    return JSONResponse({"ok": True})

@router.get("/me")
async def me(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Not logged in")
    from app.db.models import User
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"id": user.id, "email": user.email, "username": user.username, "is_admin": user.is_admin}
