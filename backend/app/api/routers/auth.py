from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.crud.users import get_by_email_or_username
from app.core.security import verify_password

router = APIRouter()

class LoginJSON(BaseModel):
    identifier: str
    password: str

@router.post("/api/login")
async def api_login(
    request: Request,
    db: Session = Depends(get_db),
    # JSON-Body (optional)
    payload: LoginJSON | None = None,
    # Form-Felder (optional)
    identifier: str | None = Form(default=None),
    password: str | None = Form(default=None),
):
    # Werte aus JSON ODER Form holen
    ident = identifier or (payload.identifier if payload else None)
    pwd   = password   or (payload.password   if payload else None)

    if not ident or not pwd:
        return JSONResponse({"detail": "missing credentials"}, status_code=400)

    user = get_by_email_or_username(db, ident)
    if not user or not verify_password(pwd, user.password_hash):
        return JSONResponse({"detail": "invalid credentials"}, status_code=401)

    # Session setzen
    request.session["uid"] = user.id
    request.session["username"] = user.username
    request.session["is_admin"] = bool(getattr(user, "is_admin", False))

    # HTML-Client? -> Redirect (Support für ?next=)
    accept = request.headers.get("accept", "")
    ctype  = request.headers.get("content-type", "")
    if "text/html" in accept or "application/x-www-form-urlencoded" in ctype:
        next_url = request.query_params.get("next") or "/"
        return RedirectResponse(next_url, status_code=303)

    # API-Client -> JSON
    return JSONResponse({"ok": True})

@router.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear()
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"ok": True})
