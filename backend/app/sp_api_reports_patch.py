from __future__ import annotations

import csv
import gzip
import json
import time
import base64
from io import BytesIO, StringIO
from typing import List, Dict, Any
from datetime import datetime, timezone

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .sp_api import _sp_request, _iso8601s, EU_MK_IDS

# EU-Default Marketplace-IDs (DE, FR, IT, ES)
EU_DEFAULT_MIDS = [EU_MK_IDS[m] for m in ("DE","FR","IT","ES") if m in EU_MK_IDS]

# Offizielle SP-API Report-Typen (ohne führende/abschließende Unterstriche!)
R_CUSTOMER_RETURNS   = "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA"
R_REMOVALS           = "GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA"
R_ADJUSTMENTS = "GET_FBA_FULFILLMENT_INVENTORY_ADJUSTMENTS_DATA"
R_REIMBURSEMENTS     = "GET_FBA_REIMBURSEMENTS_DATA"

# Fallback-Mapping von numerischen Codes (falls je numerisch reingegeben)
REPORT_CODE_MAP = {
    "2605": R_ADJUSTMENTS,  # bekannte Zuordnung
}

def _normalize_report_type(rt: str) -> str:
    """Entfernt MWS-Unterstriche und mappt evtl. numerische Codes auf SP-API Namen."""
    rt = (rt or "").strip()
    if rt.startswith("_") and rt.endswith("_"):
        rt = rt[1:-1]
    if rt.isdigit():
        rt = REPORT_CODE_MAP.get(rt, rt)
    return rt

# ---------- Helpers ----------

def _create_report(account_id:int, enc_refresh_token:str, report_type:str,
                   start:datetime, end:datetime, marketplace_ids:List[str]|None=None) -> str|None:
    rt = _normalize_report_type(report_type)
    body = {
        "reportType": rt,
        "dataStartTime": _iso8601s(start),
        "dataEndTime": _iso8601s(end),
        "marketplaceIds": marketplace_ids or EU_DEFAULT_MIDS,
    }
    try:
        r = _sp_request(account_id, enc_refresh_token, "POST", "/reports/2021-06-30/reports", body=body)
        rep_id = r.json().get("payload", {}).get("reportId")
        return rep_id
    except Exception as e:
        msg = str(e)
        # Manche Konten/Zeiträume lassen bestimmte Typen temporär nicht zu
        if "not allowed at this time" in msg.lower():
            return None
        # Falls eine Fehlermeldung "marketplaceIds missing" zurückkommt, nochmal ohne schicken
        if "marketplaceids" in msg.lower() and "missing" in msg.lower():
            body.pop("marketplaceIds", None)
            r = _sp_request(account_id, enc_refresh_token, "POST", "/reports/2021-06-30/reports", body=body)
            return r.json().get("payload", {}).get("reportId")
        # Falls irgendwo noch ein Typ mit Unterstrichen reinkam, letzter Versuch ohne
        if "GET" in rt or rt.endswith("_"):
            body["reportType"] = _normalize_report_type(rt)
            r = _sp_request(account_id, enc_refresh_token, "POST", "/reports/2021-06-30/reports", body=body)
            return r.json().get("payload", {}).get("reportId")
        raise

def _poll_report(account_id:int, enc_refresh_token:str, report_id:str, timeout_s:int=180) -> Dict[str,Any]|None:
    t0 = time.time()
    while time.time()-t0 < timeout_s:
        r = _sp_request(account_id, enc_refresh_token, "GET", f"/reports/2021-06-30/reports/{report_id}")
        pl = r.json().get("payload", {})
        st = pl.get("processingStatus")
        if st in ("DONE","FATAL","CANCELLED"):
            return pl
        time.sleep(3)
    return None

def _aes_cbc_decrypt(key_b64:str, iv_b64:str, data:bytes) -> bytes:
    key = base64.b64decode(key_b64)
    iv  = base64.b64decode(iv_b64)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    dec = decryptor.update(data) + decryptor.finalize()
    # PKCS#7 Padding entfernen
    pad = dec[-1]
    if isinstance(pad, int) and 1 <= pad <= 16:
        dec = dec[:-pad]
    return dec

def _download_document(url:str, encryption:Dict[str,str]|None, compression:str|None) -> bytes:
    with httpx.Client(timeout=120) as c:
        resp = c.get(url)
        resp.raise_for_status()
        blob = resp.content
    if encryption:
        blob = _aes_cbc_decrypt(encryption["key"], encryption["initializationVector"], blob)
    if compression == "GZIP":
        blob = gzip.decompress(blob)
    return blob

def _csv_rows_from_bytes(b:bytes) -> List[Dict[str,str]]:
    txt = b.decode("utf-8", errors="replace")
    delimiter = "\t"
    try:
        dialect = csv.Sniffer().sniff(txt.splitlines()[0])
        delimiter = dialect.delimiter
    except Exception:
        pass
    f = StringIO(txt)
    rdr = csv.DictReader(f, delimiter=delimiter)
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in rdr]

def _g(d:Dict[str,str], *keys:str) -> str|None:
    for k in keys:
        if k in d and d[k] != "":
            return d[k]
    return None

# ---------- Generic fetch ----------

def _fetch_generic(account_id:int, enc_refresh_token:str, report_type:str,
                   start:datetime, end:datetime) -> List[Dict[str,Any]]:
    rep_id = _create_report(account_id, enc_refresh_token, report_type, start, end)
    if not rep_id:
        return []
    polled = _poll_report(account_id, enc_refresh_token, rep_id)
    if not polled or polled.get("processingStatus") != "DONE":
        return []
    doc_id = polled.get("reportDocumentId")
    doc = _sp_request(account_id, enc_refresh_token, "GET", f"/reports/2021-06-30/documents/{doc_id}").json().get("payload", {})
    url = doc.get("url")
    enc = doc.get("encryptionDetails")
    comp = doc.get("compressionAlgorithm")
    if not url:
        return []
    raw_bytes = _download_document(url, enc, comp)
    return _csv_rows_from_bytes(raw_bytes)

# ---------- Public mappers ----------

def fetch_returns_rows(account_id:int, enc_refresh_token:str, start:datetime, end:datetime) -> List[Dict[str,Any]]:
    rows = _fetch_generic(account_id, enc_refresh_token, R_CUSTOMER_RETURNS, start, end)
    out=[]
    for r in rows:
        out.append({
            "return_date":     _g(r, "return-date", "Return date", "return_date", "Date"),
            "order_id":        _g(r, "order-id", "Order ID", "order_id", "order-id(s)"),
            "asin":            _g(r, "asin", "ASIN"),
            "sku":             _g(r, "sku", "SKU", "Merchant SKU"),
            "disposition":     _g(r, "disposition", "Disposition"),
            "reason":          _g(r, "reason", "Return reason", "Return Reason"),
            "quantity":        _g(r, "quantity", "Quantity", "Units"),
            "fc":              _g(r, "fulfillment-center-id", "FC", "fulfillment_center_id"),
            "raw":             r,
        })
    return out

def fetch_removals_rows(account_id:int, enc_refresh_token:str, start:datetime, end:datetime) -> List[Dict[str,Any]]:
    rows = _fetch_generic(account_id, enc_refresh_token, R_REMOVALS, start, end)
    out=[]
    for r in rows:
        out.append({
            "request_date":     _g(r, "request-date", "request date", "Request Date", "request_date"),
            "order_type":       _g(r, "order-type", "Order type", "order_type"),
            "description":      _g(r, "description", "Disposition detail", "detail"),
            "disposition":      _g(r, "disposition", "Disposition"),
            "order_id":         _g(r, "order-id", "Removal order ID", "order_id"),
            "sku":              _g(r, "sku", "SKU", "Merchant SKU"),
            "asin":             _g(r, "asin", "ASIN"),
            "shipped_quantity": _g(r, "shipped-quantity", "Shipped qty", "quantity", "Qty"),
            "raw":              r,
        })
    return out

def fetch_adjustments_rows(account_id:int, enc_refresh_token:str, start:datetime, end:datetime) -> List[Dict[str,Any]]:
    rows = _fetch_generic(account_id, enc_refresh_token, R_ADJUSTMENTS, start, end)
    out=[]
    for r in rows:
        out.append({
            "adjustment_date":     _g(r, "date", "adjustment-date", "Adjustment date", "adjustment_date"),
            "reason":              _g(r, "reason", "Adjustment reason"),
            "disposition":         _g(r, "disposition", "Disposition"),
            "sku":                 _g(r, "sku", "SKU", "Merchant SKU"),
            "asin":                _g(r, "asin", "ASIN"),
            "quantity_difference": _g(r, "quantity", "Quantity", "qty", "quantity-difference"),
            "raw":                 r,
        })
    return out

def fetch_reimbursements_rows(account_id:int, enc_refresh_token:str, start:datetime, end:datetime) -> List[Dict[str,Any]]:
    rows = _fetch_generic(account_id, enc_refresh_token, R_REIMBURSEMENTS, start, end)
    out=[]
    for r in rows:
        out.append({
            "reimbursement_date": _g(r, "reimbursement-date", "Posted date", "date"),
            "reimbursement_id":   _g(r, "reimbursement-id", "Reimbursement ID", "id"),
            "reason":             _g(r, "reason", "Reimbursement reason"),
            "amount":             _g(r, "amount", "Amount"),
            "currency":           _g(r, "currency", "Currency"),
            "sku":                _g(r, "sku", "SKU", "Merchant SKU"),
            "asin":               _g(r, "asin", "ASIN"),
            "order_id":           _g(r, "order-id", "Order ID", "order_id"),
            "raw":                r,
        })
    return out
