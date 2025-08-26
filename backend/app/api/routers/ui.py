from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.api.deps import require_auth

router = APIRouter()

@router.get("/")
def root():
    return RedirectResponse("/ui")

@router.get("/ui", response_class=HTMLResponse)
def ui_page(request: Request, _=Depends(require_auth)):
    return HTMLResponse("<!doctype html><html><body><h2>Dashboard</h2><p>Login OK. UI folgt…</p></body></html>")
@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page():
    # Einfache Inline-Loginseite, POST geht als JSON an /api/login
    return """
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <title>Login</title>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 2rem; background:#0b1220; color:#e7eef8; }
    .card { max-width: 420px; margin: 6vh auto; background: #121a2a; border-radius: 16px; padding: 24px; box-shadow: 0 20px 40px rgba(0,0,0,0.35); }
    h1 { margin: 0 0 0.5rem 0; font-size: 1.4rem; }
    p.sub { margin: 0 0 1.2rem 0; opacity: .8; }
    label { display:block; margin:.75rem 0 .35rem; font-size:.95rem; }
    input { width:100%; padding:.75rem .9rem; border-radius:10px; border:1px solid #2a3758; background:#0f1626; color:#e7eef8; }
    button { width:100%; margin-top:1rem; padding:.8rem 1rem; border:0; border-radius:10px; background:#2f6df6; color:white; font-weight:600; cursor:pointer; }
    button:disabled { opacity:.6; cursor:not-allowed; }
    .msg { margin-top:.75rem; min-height:1.2rem; font-size:.9rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Seller Control – Login</h1>
    <p class="sub">Bitte anmelden</p>
    <form id="loginForm">
      <label for="identifier">E-Mail oder Benutzername</label>
      <input id="identifier" name="identifier" autocomplete="username" required />
      <label for="password">Passwort</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required />
      <button id="loginBtn" type="submit">Einloggen</button>
      <div id="msg" class="msg"></div>
    </form>
  </div>

  <script>
    const f = document.getElementById('loginForm');
    const btn = document.getElementById('loginBtn');
    const msg = document.getElementById('msg');

    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      msg.textContent = '';
      btn.disabled = true;

      const identifier = document.getElementById('identifier').value.trim();
      const password = document.getElementById('password').value;

      try {
        const res = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ identifier, password })
        });

        if (res.ok) {
          // erfolgreich -> Startseite aufrufen (wird serverseitig ggf. auf UI weiterleiten)
          window.location.href = '/';
        } else if (res.status === 401) {
          msg.textContent = 'Login fehlgeschlagen.';
        } else if (res.status === 405) {
          msg.textContent = 'Falsche Methode (405) – API erwartet POST.';
        } else if (res.status === 422) {
          msg.textContent = 'Ungültige Eingabedaten (422) – Feldnamen prüfen.';
        } else {
          const t = await res.text();
          msg.textContent = 'Fehler: ' + (t || res.status);
        }
      } catch (err) {
        msg.textContent = 'Netzwerkfehler: ' + err;
      } finally {
        btn.disabled = false;
      }
    });
  </script>
</body>
</html>
    """
