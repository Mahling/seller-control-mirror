from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime, timedelta, timezone
import os, time, json, urllib.parse

import httpx
from botocore.credentials import Credentials as BotoCreds
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from .crypto import decrypt

ENDPOINT_BY_REGION = {
    "eu": "https://sellingpartnerapi-eu.amazon.com",
    "na": "https://sellingpartnerapi-na.amazon.com",
    "fe": "https://sellingpartnerapi-fe.amazon.com",
}
AWS_REGION_FOR_SP = {"eu": "eu-west-1", "na": "us-east-1", "fe": "us-west-2"}

EU_MK_IDS = {
    "DE":"A1PA6795UKMFR9","FR":"A13V1IB3VIYZZH","IT":"APJ6JRA9NG5V4","ES":"A1RKKUPIHCS9HS",
    "NL":"A1805IZSGTT6HS","SE":"A2NODRKZP88ZB9","PL":"A1C3SOZRARQ6R3","BE":"AMEN7PMS3EDDL","UK":"A1F83G8C2ARO7P",
}

LWA_CLIENT_ID = os.getenv("LWA_CLIENT_ID")
LWA_CLIENT_SECRET = os.getenv("LWA_CLIENT_SECRET")
SP_REGION = os.getenv("SP_REGION","eu")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
NO_AWS_MODE = os.getenv("NO_AWS_MODE","0") == "1"

BASE_URL = ENDPOINT_BY_REGION[SP_REGION]
AWS_EXEC_REGION = AWS_REGION_FOR_SP[SP_REGION]

_LWA_CACHE: Dict[int, Tuple[str, float]] = {}

def _iso8601s(dt: datetime) -> str:
    """ISO8601 in UTC mit Sekundenpräzision (keine Mikrosekunden)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    dt = dt.replace(microsecond=0)
    return dt.isoformat().replace("+00:00","Z")

def _get_lwa_access_token(account_id: int, encrypted_refresh_token: str) -> str:
    tok, exp = _LWA_CACHE.get(account_id, (None, 0))
    now = time.time()
    if tok and now < exp - 60:
        return tok
    refresh_token = decrypt(encrypted_refresh_token)
    data = {"grant_type":"refresh_token","refresh_token":refresh_token,
            "client_id":LWA_CLIENT_ID,"client_secret":LWA_CLIENT_SECRET}
    with httpx.Client(timeout=30) as c:
        r = c.post("https://api.amazon.com/auth/o2/token",
                   data=data,
                   headers={"Content-Type":"application/x-www-form-urlencoded;charset=UTF-8"})
    r.raise_for_status()
    j = r.json()
    _LWA_CACHE[account_id] = (j["access_token"], now + int(j.get("expires_in",3600)))
    return j["access_token"]

def _sign_if_needed(method: str, url: str, body: bytes|None, base_headers: Dict[str,str]) -> Dict[str,str]:
    if NO_AWS_MODE or not (AWS_ACCESS_KEY and AWS_SECRET_KEY):
        return base_headers  # LWA-only (ohne SigV4)
    creds = BotoCreds(AWS_ACCESS_KEY, AWS_SECRET_KEY)
    req = AWSRequest(method=method, url=url, data=body or b"", headers=base_headers.copy())
    SigV4Auth(creds, "execute-api", AWS_EXEC_REGION).add_auth(req)
    return dict(req.headers.items())

def _sp_request(account_id:int, enc_rtok:str, method:str, path:str,
                params:Dict[str,Any]|None=None, body:Any|None=None) -> httpx.Response:
    at = _get_lwa_access_token(account_id, enc_rtok)
    q = f"?{urllib.parse.urlencode(params, doseq=True)}" if params else ""
    url = f"{BASE_URL}{path}{q}"
    # --- normalize reportType if present (fix MWS-style names like _GET_..._) ---
    if isinstance(body, dict) and "reportType" in body:
        rt = body.get("reportType")
        if isinstance(rt, str) and rt.startswith("_") and rt.endswith("_"):
            body["reportType"] = rt.strip("_")
    body_bytes = json.dumps(body).encode() if body is not None else None
    base_headers = {
        "x-amz-access-token": at,
        "Authorization": f"Bearer {at}",
        "content-type": "application/json",
        "user-agent": "seller-control/0.1",
        "host": urllib.parse.urlparse(BASE_URL).netloc,
    }
    headers = _sign_if_needed(method, url, body_bytes, base_headers)

    with httpx.Client(timeout=60) as c:
        r = c.request(method, url, headers=headers, content=body_bytes)

    # Klare Fehlermeldung bei 4xx/5xx, inkl. Body
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        msg = json.dumps(detail)
        # Hilfreicher Hinweis, falls Signatur fehlt.
        if r.status_code in (401,403) and ("Signature" in msg or "MissingAuthenticationToken" in msg):
            raise RuntimeError("Amazon lehnt ohne AWS SigV4 ab. Bitte AWS_ACCESS_KEY/AWS_SECRET_KEY in .env setzen.")
        raise RuntimeError(f"SP-API {r.status_code} {url} -> {msg}")
    return r

def pull_orders(account_cfg:dict, account_id:int, enc_refresh_token:str,
                date_from:datetime, date_to:datetime) -> List[dict]:
    # 1) Zeiten: CreatedBefore muss mind. ~2 Minuten zurückliegen, keine Mikrosekunden.
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    safe_to = min(date_to.replace(tzinfo=timezone.utc), now_utc - timedelta(minutes=3))
    safe_from = min(date_from.replace(tzinfo=timezone.utc), safe_to - timedelta(days=1))
    if safe_from >= safe_to:
        safe_from = safe_to - timedelta(hours=1)

    # 2) Marketplaces zusammenstellen
    mks = [m.strip().upper() for m in (account_cfg.get("marketplaces") or "DE").split(",")]
    mk_ids = [EU_MK_IDS[m] for m in mks if m in EU_MK_IDS]
    # Orders API akzeptiert beides (repeated oder CSV). Wir nutzen CSV.
    params = {
        "MarketplaceIds": ",".join(mk_ids),
        "CreatedAfter": _iso8601s(safe_from),
        "CreatedBefore": _iso8601s(safe_to),
    }

    data = _sp_request(account_id, enc_refresh_token, "GET", "/orders/v0/orders", params=params).json()
    orders = data.get("payload", {}).get("Orders", [])

    out=[]
    for o in orders[:20]:
        oid = o.get("AmazonOrderId")
        try:
            items = _sp_request(account_id, enc_refresh_token, "GET",
                                f"/orders/v0/orders/{oid}/orderItems").json().get("payload",{}).get("OrderItems",[])
        except Exception:
            items=[]
        out.append({
            "orderId": oid,
            "purchaseDate": o.get("PurchaseDate"),
            "status": o.get("OrderStatus"),
            "marketplaceId": o.get("MarketplaceId"),
            "items": [{"asin":it.get("ASIN"),"sku":it.get("SellerSKU"),
                       "qty":it.get("QuantityOrdered"),
                       "price":(it.get("ItemPrice",{}) or {}).get("Amount"),
                       "currency":(it.get("ItemPrice",{}) or {}).get("CurrencyCode")} for it in items],
        })
    return out
