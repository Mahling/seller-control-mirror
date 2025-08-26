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

