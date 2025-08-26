from __future__ import annotations
import re
from typing import List, Dict, Any
from datetime import datetime
import time, io, csv, gzip, httpx

# wir nutzen die vorhandenen SP-API Hilfen
from .sp_api import _sp_request, _iso8601s, EU_MK_IDS

# Fallback auf alle EU-Marketplaces, falls Amazon welche fordert
EU_DEFAULT_MIDS = list(EU_MK_IDS.values())

# ✅ Offizielle Report-Typen für das FBA-Recon-Usecase
R_CUSTOMER_RETURNS   = "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA"
R_REMOVALS           = "GET_FBA_FULFILLMENT_REMOVALS_ORDER_DETAIL_DATA"
R_ADJUSTMENTS        = "GET_FBA_FULFILLMENT_INVENTORY_ADJUSTMENTS_DATA"
R_REIMBURSEMENTS     = "GET_FBA_REIMBURSEMENTS_DATA"

def _create_report(account_id:int, enc_refresh_token:str, report_type:str,
                   start:datetime, end:datetime, marketplace_ids: List[str] | None = None) -> str:
    body = {
        "reportType": report_type,
        "dataStartTime": _iso8601s(start),
        "dataEndTime": _iso8601s(end),
    }
    # Marketplace-IDs dazulegen (einige FBA-Reports erwarten sie)
    body["marketplaceIds"] = marketplace_ids or EU_DEFAULT_MIDS

    r = _sp_request(account_id, enc_refresh_token, "POST", "/reports/2021-06-30/reports", body=body)
    j = r.json()
    payload = j.get("payload") or j
    rep_id = payload.get("reportId")
    if not rep_id:
        raise RuntimeError(f"Create report failed: {j}")
    return rep_id

def _wait_report_done(account_id:int, enc_refresh_token:str, report_id:str,
                      timeout:int = 360, sleep_s:int = 5) -> str:
    deadline = time.time() + timeout
    while True:
        r = _sp_request(account_id, enc_refresh_token, "GET", f"/reports/2021-06-30/reports/{report_id}")
        j = r.json()
        p = j.get("payload") or j
        st = p.get("processingStatus")
        if st == "DONE":
            doc_id = p.get("reportDocumentId")
            if not doc_id:
                raise RuntimeError(f"Missing document id: {j}")
            return doc_id
        if st in ("FATAL", "CANCELLED"):
            raise RuntimeError(f"Report ended with status={st}: {j}")
        if time.time() > deadline:
            raise TimeoutError(f"Report not DONE within {timeout}s (last={st})")
        time.sleep(sleep_s)

def _download_document(url: str, compression: str | None = None) -> bytes:
    with httpx.Client(timeout=60) as c:
        r = c.get(url)
        r.raise_for_status()
        data = r.content
    # Viele FBA-Flatfiles sind GZIP-komprimiert
    if compression and compression.upper() == "GZIP":
        try:
            data = gzip.decompress(data)
        except Exception:
            pass
    return data

def _get_document_and_rows(account_id:int, enc_refresh_token:str, document_id:str) -> List[Dict[str, Any]]:
    r = _sp_request(account_id, enc_refresh_token, "GET", f"/reports/2021-06-30/documents/{document_id}")
    j = r.json()
    p = j.get("payload") or j
    url = p["url"]
    compression = p.get("compressionAlgorithm")
    raw = _download_document(url, compression)

    text = raw.decode("utf-8", errors="replace")
    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except Exception:
        # einfache Heuristik für Tab vs. Komma
        dialect = csv.excel_tab if sample.count("\t") > sample.count(",") else csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = [dict(r) for r in reader]
    print(f"[reports] doc rows={len(rows)} head={rows[:2]}")
    return rows

def _fetch_generic(account_id:int, enc_refresh_token:str, report_type:str,
                   start:datetime, end:datetime, mk_ids: List[str] | None = None) -> List[Dict[str, Any]]:
    rep_id = _create_report_tolerant(account_id, enc_refresh_token, report_type, start, end, mk_ids)
    doc_id = _wait_report_done(account_id, enc_refresh_token, rep_id)
    rows = _get_document_and_rows(account_id, enc_refresh_token, doc_id)
    return rows

# ---------- Public helpers (werden in main.py genutzt) ----------

def fetch_returns_rows(account_id:int, enc_refresh_token:str, start:datetime, end:datetime):
    rows = _fetch_generic(account_id, enc_refresh_token, R_CUSTOMER_RETURNS, start, end)
    out = []
    for r in rows:
        out.append({
            "return_date": r.get("return-date") or r.get("return_date") or r.get("ReturnDate"),
            "order_id": r.get("order-id") or r.get("order_id") or r.get("OrderId"),
            "asin": r.get("asin") or r.get("ASIN"),
            "sku": r.get("sku") or r.get("seller-sku") or r.get("SellerSKU"),
            "disposition": r.get("disposition") or r.get("Disposition"),
            "reason": r.get("reason") or r.get("Reason"),
            "quantity": _to_int(r.get("quantity") or r.get("Quantity")),
            "fc": r.get("fulfillment-center-id") or r.get("fc"),
            "raw": r,
        })
    return out

def fetch_removals_rows(account_id:int, enc_refresh_token:str, start:datetime, end:datetime):
    rows = _fetch_generic(account_id, enc_refresh_token, R_REMOVALS, start, end)
    out = []
    for r in rows:
        out.append({
            "request_date": r.get("request-date") or r.get("request_date"),
            "order_id": r.get("order-id") or r.get("order_id"),
            "asin": r.get("asin") or r.get("ASIN"),
            "sku": r.get("sku") or r.get("seller-sku") or r.get("SellerSKU"),
            "quantity": _to_int(r.get("quantity")),
            "disposition": r.get("disposition") or r.get("removal-disposition"),
            "fc": r.get("fulfillment-center") or r.get("fc"),
            "raw": r,
        })
    return out

def fetch_adjustments_rows(account_id:int, enc_refresh_token:str, start:datetime, end:datetime):
    rows = _fetch_generic(account_id, enc_refresh_token, R_ADJUSTMENTS, start, end)
    out = []
    for r in rows:
        out.append({
            "date": r.get("date") or r.get("posted-date") or r.get("adjusted-date"),
            "fnsku": r.get("fnsku"),
            "sku": r.get("sku") or r.get("seller-sku"),
            "asin": r.get("asin"),
            "quantity": _to_int(r.get("quantity") or r.get("quantity-adjusted") or r.get("quantity_total")),
            "reason": r.get("reason") or r.get("adjustment-type"),
            "raw": r,
        })
    return out

def fetch_reimbursements_rows(account_id:int, enc_refresh_token:str, start:datetime, end:datetime):
    rows = _fetch_generic(account_id, enc_refresh_token, R_REIMBURSEMENTS, start, end)
    out = []
    for r in rows:
        out.append({
            "reimbursed_date": r.get("reimbursed-date") or r.get("posted-date"),
            "reason": r.get("reason-code") or r.get("reason"),
            "amount": r.get("amount-per-unit") or r.get("amount-total") or r.get("amount"),
            "currency": r.get("currency"),
            "order_id": r.get("order-id") or r.get("order_id"),
            "asin": r.get("asin"),
            "sku": r.get("sku") or r.get("seller-sku"),
            "raw": r,
        })
    return out

def _to_int(v: Any) -> int | None:
    try:
        return int(str(v).strip()) if v not in (None, "", "NA", "N/A") else None
    except Exception:
        return None


def _create_report_tolerant(account_id, enc_refresh_token, report_type, start, end, mk_ids=None):
    """
    Create SP-API report, normalize reportType (fixes plural variants, underscores), ensure marketplaceIds,
    and parse response robustly.
    """
    from datetime import timezone
    from .sp_api import EU_MK_IDS, _sp_request

    # MWS-Style -> SP-API Style Mapping (inkl. pluraler Fehlvariante)
    TYPE_MAP = {
        "_GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA_": "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA",
        "_GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA_": "GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA",
        "_GET_FBA_FULFILLMENT_REMOVALS_ORDER_DETAIL_DATA_": "GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA",  # fix plural
        "_GET_FBA_REIMBURSEMENTS_DATA_": "GET_FBA_REIMBURSEMENTS_DATA",
        "_GET_FBA_INVENTORY_ADJUSTMENTS_DATA_": "GET_FBA_INVENTORY_ADJUSTMENTS_DATA",
    }

    # Normalisieren
    rt = TYPE_MAP.get(str(report_type).strip(), str(report_type).strip())
    # „REMOVALS“ Tippfehler → „REMOVAL“
    rt = rt.replace("REMOVALS_ORDER_DETAIL_DATA", "REMOVAL_ORDER_DETAIL_DATA")
    # Führende/abschließende Unterstriche entfernen
    if rt.startswith("_") and rt.endswith("_"):
        rt = rt.strip("_")
    # Sicherheitshalber upper-case
    rt = rt.upper()

    def _iso(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0).isoformat().replace("+00:00","Z")

    # EU-Marktplätze ohne BE (AMEN7PMS3EDDL führte zu 400)
    eu_default = [mid for k, mid in EU_MK_IDS.items() if k != "BE"]
    mids = mk_ids or eu_default

    body = {
        "reportType": rt,
        "marketplaceIds": mids,
        "dataStartTime": _iso(start),
        "dataEndTime": _iso(end),
    }

    resp = _sp_request(account_id, enc_refresh_token, "POST", "/reports/2021-06-30/reports", body=body)
    try:
        j = resp.json()
    except Exception:
        j = {}

    rep_id = (j.get("payload") or {}).get("reportId") or j.get("reportId")
    if not rep_id:
        txt = getattr(resp, "text", "")
        raise RuntimeError(f"CreateReport unexpected response: status={resp.status_code}, json={j}, text={txt[:300]}")
    return rep_id
