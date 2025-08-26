from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from urllib.parse import urlencode
from datetime import datetime
import os, httpx, secrets
from .db import get_db
from . import models
from .crypto import encrypt

router = APIRouter(prefix="/oauth", tags=["oauth"])

# Mini-State-Store im Speicher (MVP). Für Prod -> DB + Expiry.
_state_store = {}

def _settings():
    return {
        "auth_url": os.getenv("SPAPI_AUTH_URL", "").rstrip("/"),
        "app_id": os.getenv("SPAPI_APP_ID"),
        "client_id": os.getenv("LWA_CLIENT_ID"),
        "client_secret": os.getenv("LWA_CLIENT_SECRET"),
        "redirect_uri": os.getenv("LWA_REDIRECT_URI"),
        "token_url": "https://api.amazon.com/auth/o2/token",
    }

@router.get("/start")
def oauth_start(request: Request):
    s = _settings()
    if not all([s["auth_url"], s["app_id"], s["client_id"], s["client_secret"], s["redirect_uri"]]):
        raise HTTPException(500, "OAuth settings missing (check .env)")
    state = secrets.token_urlsafe(24)
    _state_store[state] = True
    params = {
        "application_id": s["app_id"],
        "state": state,
        "redirect_uri": s["redirect_uri"],
        "version": "beta",
    }
    return RedirectResponse(url=f'{s["auth_url"]}?{urlencode(params)}', status_code=302)

@router.get("/callback")
def oauth_callback(state: str | None = None,
                   selling_partner_id: str | None = None,
                   spapi_oauth_code: str | None = None,
                   db: Session = Depends(get_db)):
    s = _settings()
    if not state or state not in _state_store:
        raise HTTPException(400, "Invalid state")
    _state_store.pop(state, None)
    if not spapi_oauth_code:
        raise HTTPException(400, "Missing spapi_oauth_code")

    # Code -> Tokens tauschen
    data = {
        "grant_type": "authorization_code",
        "code": spapi_oauth_code,
        "client_id": s["client_id"],
        "client_secret": s["client_secret"],
        "redirect_uri": s["redirect_uri"],
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(s["token_url"], data=data)
        if resp.status_code != 200:
            raise HTTPException(502, f"LWA token exchange failed: {resp.text}")
        payload = resp.json()
    refresh = payload.get("refresh_token")
    if not refresh:
        raise HTTPException(502, "No refresh_token returned by LWA")

    # Account anlegen/aktualisieren (Name = SP-Account oder Zeitstempel)
    name = selling_partner_id or f"SP-Account-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    enc = encrypt(refresh)
    acc = models.SellerAccount(
        name=name,
        region="eu",
        marketplaces="DE,FR,IT,ES",
        refresh_token=enc
    )
    db.add(acc)
    db.commit()

    # zurück zum Dashboard
    html = "<script>window.location='/'</script>OAuth success. Redirecting…"
    return HTMLResponse(content=html)
