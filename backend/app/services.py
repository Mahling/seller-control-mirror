from sqlalchemy.orm import Session
from datetime import datetime
from . import models

def reconcile_account(db: Session, account_id: int, date_from: datetime, date_to: datetime) -> int:
    # Simple placeholder: roll up ledger vs reimbursements by SKU
    ledger_rows = db.query(models.InventoryLedger).filter(
        models.InventoryLedger.account_id == account_id,
        models.InventoryLedger.event_date >= date_from,
        models.InventoryLedger.event_date < date_to
    ).all()

    reimb_rows = db.query(models.Reimbursement).filter(
        models.Reimbursement.account_id == account_id,
        models.Reimbursement.posted_date >= date_from,
        models.Reimbursement.posted_date < date_to
    ).all()

    # Aggregate
    by_sku = {}
    for r in ledger_rows:
        key = (r.asin, r.sku)
        agg = by_sku.setdefault(key, {"lost":0,"damaged":0,"found":0})
        if r.event_type == "Lost":
            agg["lost"] += (r.qty or 0)
        elif r.event_type == "Damaged":
            agg["damaged"] += (r.qty or 0)
        elif r.event_type == "Found":
            agg["found"] += (r.qty or 0)

    reimb_by_sku = {}
    for r in reimb_rows:
        key = (r.asin, r.sku)
        agg = reimb_by_sku.setdefault(key, {"units":0,"amount":0.0})
        agg["units"] += (r.units or 0)
        agg["amount"] += float(r.amount or 0)

    # Upsert recon results
    inserted = 0
    for (asin, sku), m in by_sku.items():
        reimb = reimb_by_sku.get((asin, sku), {"units":0,"amount":0.0})
        open_units = (m["lost"] + m["damaged"] - m["found"]) - reimb["units"]
        db.add(models.ReconResult(
            account_id=account_id, asin=asin, sku=sku,
            window_from=date_from, window_to=date_to,
            lost_units=m["lost"], damaged_units=m["damaged"], found_units=m["found"],
            reimbursed_units=reimb["units"], reimbursed_amount=reimb["amount"],
            open_units=open_units, open_amount=0.0
        ))
        inserted += 1
    db.commit()
    return inserted
