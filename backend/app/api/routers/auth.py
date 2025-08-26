from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.crud.users import get_by_email_or_username
from app.core.security import verify_password

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def login_page() -> str:
    # schlankes HTML mit klassischem Form-Post -> Server redirectet selbst
    return """<!doctype html>
<html><head><meta charset="utf-8"><title>Login</title></head>
<body>
  <h1>Seller Control – Login</h1>
  <form method="post" action="/api/login?next=/">
    <label>Email/Username <input name="identifier" required></label><br/>
    <label>Password <input name="password" type="password" required></label><br/>
    <button type="submit">Login</button>
  </form>
</body></html>"""

@router.post("/api/login")
async def api_login(request: Request, db: Session = Depends(get_db)):
    # Sowohl JSON als auch Form akzeptieren
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        identifier = (payload or {}).get("identifier") or (payload or {}).get("username")
        password   = (payload or {}).get("password")
    else:
        form = await request.form()
        identifier = form.get("identifier") or form.get("username")
        password   = form.get("password")

    if not identifier or not password:
        raise HTTPException(status_code=400, detail="missing credentials")

    user = get_by_email_or_username(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    # Session setzen -> SessionMiddleware schreibt Set-Cookie
    request.session["uid"] = int(user.id)
    request.session["is_admin"] = bool(user.is_admin)

    # Bei echten Form/HTML-Flows serverseitig weiterleiten, sonst JSON
    next_url = request.query_params.get("next") or "/"
    if "application/x-www-form-urlencoded" in ctype or "text/html" in request.headers.get("accept", ""):
        return RedirectResponse(next_url, status_code=status.HTTP_303_SEE_OTHER)

    return JSONResponse({"ok": True})

@router.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

# Debug: aktuelle Session sehen
@router.get("/api/whoami")
async def whoami(request: Request):
    return {"session": dict(request.session)}
