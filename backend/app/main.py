from sqlalchemy import text
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import get_db
from . import models
from .crypto import encrypt
from .sp_api import pull_orders
from .sp_api_reports_patch import (
    fetch_returns_rows,
    fetch_removals_rows,
    fetch_adjustments_rows,
    fetch_reimbursements_rows,
)

app = FastAPI()
# --- sessions: muss vor jedem Middleware/Guard liegen, der request.session nutzt ---
app.add_middleware(
app.add_middleware(SessionMiddleware, secret_key=os.environ.get('SESSION_SECRET', 'changeme'), same_site='lax')


    secret_key=os.getenv("SESSION_SECRET", "dev-secret"),
    max_age=60*60*24*14,   # 14 Tage
    same_site="lax",
    https_only=True,
)

templates = Jinja2Templates(directory="templates")


def _try_parse_dt(s: Optional[str]):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)
    except Exception:
        return None


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    accounts = db.query(models.SellerAccount).order_by(models.SellerAccount.id.asc()).all()
    orders = (
        db.query(models.Order)
        .order_by(models.Order.purchase_date.desc().nullslast())
        .limit(30)
        .all()
    )
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "accounts": accounts, "orders": orders},
    )


@app.post("/api/accounts", response_class=HTMLResponse)
def create_account(
    name: str = Form(...),
    region: str = Form(...),
    marketplaces: str = Form(...),
    lwa_refresh_token: str = Form(""),
    db: Session = Depends(get_db),
):
    acc = models.SellerAccount(
        name=(name or "").strip() or "Hauptkonto",
        region=(region or "").strip() or "eu",
        marketplaces=(marketplaces or "").strip() or "DE",
        refresh_token=encrypt((lwa_refresh_token or "").strip()) if lwa_refresh_token else None,
        active=True,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return HTMLResponse(
        f"<div class='text-green-700'>Konto {acc.name} angelegt (ID {acc.id}).</div>",
        status_code=200,
    )


@app.post("/api/accounts/{account_id}/toggle")
def toggle_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.get(models.SellerAccount, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    # toleriert unterschiedliche Feldnamen
    if hasattr(acc, "is_active"):
        acc.is_active = not bool(acc.is_active)
    if hasattr(acc, "active"):
        acc.active = not bool(getattr(acc, "active"))
    db.commit()
    return {"id": acc.id, "is_active": getattr(acc, "is_active", getattr(acc, "active", True))}


# ==========================
# A) SYNC ORDERS (SP-API)
# ==========================
@app.post("/api/orders/sync")
def api_sync_orders(account_id: int, days: int = 7, db: Session = Depends(get_db)):
    acc = db.get(models.SellerAccount, account_id)
    if not acc:
        return HTMLResponse("<div class='text-red-700'>Account nicht gefunden.</div>", status_code=200)

    # Marketplaces als Liste (UI: "DE,FR,IT" etc.)
    mks_list = [m.strip().upper() for m in (acc.marketplaces or "DE").split(",") if m.strip()]
    # account_cfg so, wie sp_api.pull_orders es erwartet (string, der intern gesplittet wird)
    account_cfg = {"marketplaces": ",".join(mks_list)}

    # 2-Minuten-Puffer (Amazon-Anforderung)
    _now = datetime.utcnow()
    date_to = _now - timedelta(minutes=2)
    date_from = date_to - timedelta(days=days)

    # Kompatibler Aufruf: pull_orders(account_id, enc_refresh_token, account_cfg, date_from, date_to)
    orders = pull_orders(account_cfg, acc.id, acc.refresh_token, date_from, date_to)

    inserted = 0
    for o in orders:
        db.add(
            models.Order(
                account_id=acc.id,
                order_id=o.get("orderId"),
                purchase_date=_try_parse_dt(o.get("purchaseDate")),
                status=(o.get("status") or "")[:20],           # hart auf 20 gekappt
                marketplace=(o.get("marketplaceId") or "")[:20],# sicher < 20
                data=o,
            )
        )
        inserted += 1

        # Optional: Items (wenn Model vorhanden)
        if hasattr(models, "OrderItem"):
            for it in o.get("items", []):
                price_val = it.get("price")
                try:
                    price_val = None if price_val in (None, "") else float(price_val)
                except Exception:
                    price_val = None
                db.add(
                    models.OrderItem(
                        account_id=acc.id,
                        order_id=o.get("orderId"),
                        asin=it.get("asin"),
                        sku=it.get("sku"),
                        qty=it.get("qty"),
                        price_amount=price_val,
                    )
                )

    db.commit()
    return {"synced": inserted}


# ==========================
# B) PULL REPORTS (SP-API)
# ==========================
@app.post("/api/reports/pull", response_class=HTMLResponse)
def api_pull_reports(account_id: int, days: int = 30, db: Session = Depends(get_db)):
    acc = db.get(models.SellerAccount, account_id)
    if not acc:
        return HTMLResponse("<div class='text-red-700'>Account nicht gefunden.</div>", status_code=200)

    now = datetime.utcnow()
    safe_end = now - timedelta(minutes=5)      # Reports brauchen etwas Puffer
    safe_start = safe_end - timedelta(days=days)

    # Jede Funktion nutzt sp_api._sp_request intern; wir geben nur Fenster + Token
    rets = fetch_returns_rows(acc.id, acc.refresh_token, safe_start, safe_end)
    rems = fetch_removals_rows(acc.id, acc.refresh_token, safe_start, safe_end)
    adjs = fetch_adjustments_rows(acc.id, acc.refresh_token, safe_start, safe_end)
    reims = fetch_reimbursements_rows(acc.id, acc.refresh_token, safe_start, safe_end)

    # Persistieren
    from decimal import Decimal

    for r in rets:
        db.add(
            models.FbaReturn(
                account_id=acc.id,
                return_date=_try_parse_dt(r.get("return_date")),
                order_id=r.get("order_id"),
                asin=r.get("asin"),
                sku=r.get("sku"),
                disposition=r.get("disposition"),
                reason=r.get("reason"),
                quantity=r.get("quantity"),
                fc=r.get("fc"),
                raw=r.get("raw"),
            )
        )

    for r in rems:
        db.add(
            models.FbaRemoval(
                account_id=acc.id,
                removal_order_id=r.get("removal_order_id"),
                order_type=r.get("order_type"),
                status=r.get("status"),
                request_date=_try_parse_dt(r.get("request_date")),
                shipped_date=_try_parse_dt(r.get("shipped_date")),
                received_date=_try_parse_dt(r.get("received_date")),
                asin=r.get("asin"),
                sku=r.get("sku"),
                quantity=r.get("quantity"),
                disposition=r.get("disposition"),
                raw=r.get("raw"),
            )
        )

    for r in adjs:
        db.add(
            models.FbaInventoryAdjustment(
                account_id=acc.id,
                adjustment_date=_try_parse_dt(r.get("adjustment_date")),
                asin=r.get("asin"),
                sku=r.get("sku"),
                quantity=r.get("quantity"),
                reason=r.get("reason"),
                fc=r.get("fc"),
                raw=r.get("raw"),
            )
        )

    for r in reims:
        try:
            amt = Decimal(str(r.get("amount"))) if r.get("amount") is not None else Decimal("0")
        except Exception:
            amt = Decimal("0")
        db.add(
            models.FbaReimbursement(
                account_id=acc.id,
                posted_date=_try_parse_dt(r.get("posted_date")),
                case_id=r.get("case_id"),
                asin=r.get("asin"),
                sku=r.get("sku"),
                quantity=r.get("quantity"),
                amount=amt,
                currency=r.get("currency"),
                reason=r.get("reason"),
                raw=r.get("raw"),
            )
        )

    db.commit()
    msg = f"Reports: returns={len(rets)}, removals={len(rems)}, adjustments={len(adjs)}, reimbursements={len(reims)}"
    if (len(rets) + len(rems) + len(adjs) + len(reims)) == 0:
        msg += " — (Hinweis: Zeitraum/Permissions? 5-Min-Puffer, Rollen für FBA/Lagerbestand?)"
    return HTMLResponse(f"<div class='text-green-700'>{msg}</div>", status_code=200)


# Stub – bleibt wie gehabt
@app.post("/api/recon/run", response_class=HTMLResponse)
def run_recon(account_id: int, db: Session = Depends(get_db)):
    return HTMLResponse("<div class='text-green-700'>Recon gestartet und abgeschlossen (Stub).</div>", status_code=200)


@app.get("/ui", response_class=HTMLResponse)
def ui_page():
    return """<!doctype html>
<html lang='de'>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width, initial-scale=1'/>
  <title>Seller-Control Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
  <style>
    .card { @apply bg-white shadow rounded-2xl p-4; }
    .btn  { @apply px-4 py-2 rounded-lg bg-black text-white hover:bg-gray-800; }
    .btn2 { @apply px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200; }
    .stat { @apply text-3xl font-semibold; }
    .statlabel { @apply text-sm text-gray-500; }
    .grid4 { @apply grid gap-4 grid-cols-2 md:grid-cols-4; }
  </style>
</head>
<body class="bg-gray-50 min-h-screen">
<div class="max-w-6xl mx-auto px-4 py-6">
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-2xl font-bold">Seller-Control Dashboard</h1>
    <a href="/" class="text-sm text-blue-600 hover:underline">klassische Ansicht</a>
  </div>

  <!-- Controls -->
  <div class="grid md:grid-cols-2 gap-4">
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Aktionen</h2>
      </div>
      <div class="space-y-3">
        <div>
          <label class="block text-sm text-gray-600 mb-1">Account ID</label>
          <input id="accId" type="number" class="w-full border rounded-lg px-3 py-2" placeholder="z.B. 1" value="1">
        </div>
        <div class="flex gap-2 flex-wrap">
          <button class="btn" onclick="syncOrders()">Sync Orders (7 Tage)</button>
          <button class="btn2" onclick="pullReports()">Pull Reports</button>
          <button class="btn2" onclick="runRecon()">Run Recon</button>
        </div>
        <div id="msg" class="text-sm text-gray-700"></div>
      </div>
    </div>

    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Report-Übersicht</h2>
      </div>
      <div class="grid4">
        <div><div id="c_returns" class="stat">–</div><div class="statlabel">Returns</div></div>
        <div><div id="c_removals" class="stat">–</div><div class="statlabel">Removals</div></div>
        <div><div id="c_adjustments" class="stat">–</div><div class="statlabel">Ledger Events</div></div>
        <div><div id="c_reims" class="stat">–</div><div class="statlabel">Reimbursements</div></div>
      </div>
    </div>
  </div>

  <!-- Output -->
  <div class="card mt-4">
    <h2 class="text-lg font-semibold mb-2">Ausgabe</h2>
    <div id="out" class="prose max-w-none whitespace-pre-wrap text-sm"></div>
  </div>
</div>

<script>
function q(id){ return document.getElementById(id); }
function setMsg(t){ q('msg').textContent = t; }
function setOut(html){ q('out').innerHTML = html; }
function setCounts(c){
  if(!c) return;
  q('c_returns').textContent = c.returns ?? '–';
  q('c_removals').textContent = c.removals ?? '–';
  q('c_adjustments').textContent = c.adjustments ?? '–';
  q('c_reims').textContent = c.reimbursements ?? '–';
}

function parseCountsFromHtml(html){
  const m = html.match(/returns=(\d+).*?removals=(\d+).*?adjustments=(\d+).*?reimbursements=(\d+)/i);
  if(!m) return null;
  return {returns:+m[1], removals:+m[2], adjustments:+m[3], reimbursements:+m[4]};
}

async function syncOrders(){
  const id = q('accId').value || 1;
  setMsg('Orders werden synchronisiert …');
  try{
    const r = await fetch(`/api/orders/sync?account_id=${id}&days=7`, {method:'POST'});
    const j = await r.json();
    setMsg(`✅ Orders: ${JSON.stringify(j)}`);
  }catch(e){
    setMsg('❌ ' + e);
  }
}

async function pullReports(){
  const id = q('accId').value || 1;
  setMsg('Reports werden gezogen …');
  try{
    const r = await fetch(`/api/reports/pull?account_id=${id}`, {method:'POST'});
    const t = await r.text(); // Endpoint liefert HTML
    setOut(t);
    setMsg('✅ Reports aktualisiert');
    setCounts(parseCountsFromHtml(t));
  }catch(e){
    setMsg('❌ ' + e);
  }
}

async function runRecon(){
  const id = q('accId').value || 1;
  setMsg('Recon wird ausgeführt …');
  try{
    const r = await fetch(`/api/recon/run?account_id=${id}`, {method:'POST'});
    const t = await r.text();
    setOut(t);
    setMsg('✅ Recon fertig');
  }catch(e){
    setMsg('❌ ' + e);
  }
}
</script>
</body></html>"""



# ======== AUTH & SESSIONS (appended) ========
import os
from fastapi import Request, Form, Depends
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session as SASession
from .auth import ensure_users_table, find_user, verify_password

# Session-Cookies signieren
)

# Guard-Middleware: ohne Login -> redirect /login (HTML) bzw. 401 (API)
@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    path = request.url.path
    public = (
        path == "/login"
        or path.startswith("/docs")
        or path.startswith("/openapi.json")
        or path.startswith("/api/auth/")
        or path.startswith("/favicon")
        or path == "/healthz"
        # statics, wenn du welche hast:
        or path.startswith("/static")
    )
    if public:
        return await call_next(request)
    if request.session.get("uid"):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return RedirectResponse("/login", status_code=302)

# kleine Helfer
def _get_db():
    # nutzt dein bestehendes get_db-Dependency
    from .main import get_db as _gdb   # type: ignore
    return _gdb

def _login_page(msg: str = "") -> str:
    return f"""<!doctype html>
<html lang='de'><head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>Login · Seller-Control</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head><body class="bg-gray-50 min-h-screen flex items-center justify-center">
  <form method="post" action="/login" class="bg-white shadow rounded-2xl p-6 w-full max-w-md space-y-4">
    <h1 class="text-xl font-semibold text-center">Anmeldung</h1>
    {('<div class="text-red-600 text-sm text-center">'+msg+'</div>') if msg else ''}
    <div>
      <label class="block text-sm text-gray-600 mb-1">E-Mail oder Benutzername</label>
      <input name="login" class="w-full border rounded-lg px-3 py-2" placeholder="you@example.com" required>
    </div>
    <div>
      <label class="block text-sm text-gray-600 mb-1">Passwort</label>
      <input name="password" type="password" class="w-full border rounded-lg px-3 py-2" required>
    </div>
    <button class="w-full bg-black text-white rounded-lg py-2">Einloggen</button>
  </form>
</body></html>"""

@app.get("/login", response_class=HTMLResponse)
def login_form(db: SASession = Depends(get_db)):
    # sicherstellen, dass Tabelle existiert
    ensure_users_table(db)
    return HTMLResponse(_login_page())

@app.post("/login")
def login_submit(request: Request, login: str = Form(...), password: str = Form(...), db: SASession = Depends(get_db)):
    ensure_users_table(db)
    u = find_user(db, login)
    if not u or not u["is_active"] or not verify_password(password, u["password_hash"]):
        return HTMLResponse(_login_page("Anmeldung fehlgeschlagen."), status_code=401)
    request.session["uid"] = int(u["id"])
    return RedirectResponse("/", status_code=302)

@app.post("/api/auth/logout")
@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    # für API und Form gleichermaßen sinnvoll
    if request.headers.get("accept", "").startswith("application/json"):
        return {"ok": True}
    return RedirectResponse("/login", status_code=302)

@app.get("/api/auth/me")
def me(request: Request, db: SASession = Depends(get_db)):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    row = db.execute(
        text("SELECT id, email, username FROM sc_users WHERE id=:i"),
        {"i": uid},
    ).mappings().first()
    return row or JSONResponse({"detail": "not found"}, status_code=404)
# ======== END AUTH ========
