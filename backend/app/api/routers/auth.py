from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.crud.users import get_by_email_or_username
from app.core.security import verify_password

router = APIRouter()

@router.post("/api/login")
async def api_login(request: Request, db: Session = Depends(get_db)):
    ident = None
    pwd = None

    ctype = (request.headers.get("content-type") or "").lower()
    # JSON-Body?
    if ctype.startswith("application/json"):
        try:
            data = await request.json()
            if isinstance(data, dict):
                ident = data.get("identifier") or data.get("email") or data.get("username")
                pwd = data.get("password")
        except Exception:
            pass
    else:
        # Form-Body (x-www-form-urlencoded / multipart)
        try:
            form = await request.form()
            ident = form.get("identifier") or form.get("email") or form.get("username")
            pwd = form.get("password")
        except Exception:
            pass

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
    if "text/html" in accept or not ctype.startswith("application/json"):
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
