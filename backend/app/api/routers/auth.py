from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.db.crud.users import get_by_login
from app.core.security import verify_password

router = APIRouter()

LOGIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Login</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto;display:grid;place-items:center;height:100vh;background:#0b1220;color:#e6e8ee}
.card{background:#121c30;padding:24px 28px;border-radius:16px;min-width:320px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
input{width:100%;padding:10px 12px;margin:6px 0;border-radius:8px;border:1px solid #23324d;background:#0e182b;color:#dfe3ee}
button{width:100%;padding:10px 12px;margin-top:10px;border-radius:8px;border:none;background:#3b82f6;color:white;font-weight:600}
label{font-size:12px;color:#9fb0cf}
h1{font-size:18px;margin:0 0 10px 0}
p.err{color:#ff8080}
</style></head><body>
<div class="card">
  <h1>Seller Control – Login</h1>
  {err}
  <form method="post" action="/api/login">
    <label>Login (E-Mail oder Benutzername)</label>
    <input type="text" name="login" placeholder="mail@domain.tld" required />
    <label>Passwort</label>
    <input type="password" name="password" placeholder="••••••••" required />
    <button type="submit">Einloggen</button>
  </form>
</div>
</body></html>"""

@router.get("/login", response_class=HTMLResponse)
def get_login():
    return HTMLResponse(LOGIN_HTML.replace("{err}", ""))

@router.post("/api/login")
async def post_login(request: Request, db: Session = Depends(get_db)):
    # JSON oder Form akzeptieren
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    login = data.get("login") or data.get("email") or data.get("username")
    password = data.get("password") or ""
    if not login or not password:
        return JSONResponse({"ok": False, "error": "Missing credentials"}, status_code=status.HTTP_400_BAD_REQUEST)

    user = get_by_login(db, login.strip())
    if not user or not verify_password(password, user.password_hash):
        # Wenn Browser/HTML-Form: zurück auf /login mit Fehlermeldung
        if "text/html" in request.headers.get("accept",""):
            html = LOGIN_HTML.replace("{err}", '<p class="err">Login fehlgeschlagen</p>')
            return HTMLResponse(html, status_code=status.HTTP_401_UNAUTHORIZED)
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)

    request.session["uid"] = user.id
    request.session["is_admin"] = bool(user.is_admin)
    # Browser → Redirect; API → JSON
    if "text/html" in request.headers.get("accept",""):
        return RedirectResponse("/ui", status_code=status.HTTP_302_FOUND)
    return JSONResponse({"ok": True})

@router.post("/api/logout")
def post_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
