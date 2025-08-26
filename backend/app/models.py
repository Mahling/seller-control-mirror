from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Boolean, Numeric, JSON
from datetime import datetime
from .db import Base
from sqlalchemy import Column, Integer, String, DateTime, JSON, Numeric, ForeignKey

class SellerAccount(Base):
    __tablename__ = "seller_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(10), default="eu")
    marketplaces: Mapped[str] = mapped_column(String(200), default="DE,FR,IT,ES")
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional overrides (else use env defaults)
    lwa_client_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lwa_client_secret: Mapped[str | None] = mapped_column(String(200), nullable=True)
    aws_access_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    aws_secret_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role_arn: Mapped[str | None] = mapped_column(String(300), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    order_id: Mapped[str] = mapped_column(String(40), index=True)
    purchase_date: Mapped[datetime | None]
    status: Mapped[str | None] = mapped_column(String(40))
    marketplace: Mapped[str | None] = mapped_column(String(10))
    data: Mapped[dict | None] = mapped_column(JSON)

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    order_id: Mapped[str] = mapped_column(String(40), index=True)
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    qty: Mapped[int | None] = mapped_column(Integer)
    price_amount: Mapped[float | None] = mapped_column(Numeric(12,2))
    currency: Mapped[str | None] = mapped_column(String(3))

class ReturnFBA(Base):
    __tablename__ = "returns_fba"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    return_date: Mapped[datetime | None] = mapped_column(DateTime)
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    disposition: Mapped[str | None] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(String(200))
    fc: Mapped[str | None] = mapped_column(String(20))
    qty: Mapped[int | None] = mapped_column(Integer)

class ReturnFBM(Base):
    __tablename__ = "returns_fbm"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    return_date: Mapped[datetime | None] = mapped_column(DateTime)
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    reason: Mapped[str | None] = mapped_column(String(200))
    qty: Mapped[int | None] = mapped_column(Integer)

class RemovalOrder(Base):
    __tablename__ = "removals_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    removal_order_id: Mapped[str | None] = mapped_column(String(50), index=True)
    order_type: Mapped[str | None] = mapped_column(String(20))  # Return/Disposal
    status: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)

class RemovalShipment(Base):
    __tablename__ = "removals_shipments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    removal_order_id: Mapped[str | None] = mapped_column(String(50), index=True)
    tracking: Mapped[str | None] = mapped_column(String(60))
    qty: Mapped[int | None] = mapped_column(Integer)
    received_date: Mapped[datetime | None] = mapped_column(DateTime)

class InventoryLedger(Base):
    __tablename__ = "inventory_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    event_type: Mapped[str | None] = mapped_column(String(40))  # Lost/Damaged/Found/Adjustment
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    fc: Mapped[str | None] = mapped_column(String(20))
    qty: Mapped[int | None] = mapped_column(Integer)
    reference: Mapped[str | None] = mapped_column(String(80))

class Reimbursement(Base):
    __tablename__ = "reimbursements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    posted_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    case_id: Mapped[str | None] = mapped_column(String(60))
    reason: Mapped[str | None] = mapped_column(String(200))
    units: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[float | None] = mapped_column(Numeric(12,2))

class ReconResult(Base):
    __tablename__ = "recon_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("seller_accounts.id"), index=True)
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(80), index=True)
    window_from: Mapped[datetime | None] = mapped_column(DateTime)
    window_to: Mapped[datetime | None] = mapped_column(DateTime)
    lost_units: Mapped[int | None] = mapped_column(Integer, default=0)
    damaged_units: Mapped[int | None] = mapped_column(Integer, default=0)
    found_units: Mapped[int | None] = mapped_column(Integer, default=0)
    reimbursed_units: Mapped[int | None] = mapped_column(Integer, default=0)
    reimbursed_amount: Mapped[float | None] = mapped_column(Numeric(12,2), default=0)
    open_units: Mapped[int | None] = mapped_column(Integer, default=0)
    open_amount: Mapped[float | None] = mapped_column(Numeric(12,2), default=0)


class FbaReturn(Base):
    __tablename__ = "fba_returns"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("seller_accounts.id"), index=True, nullable=False)
    return_date = Column(DateTime, index=True)
    order_id = Column(String(40), index=True)
    asin = Column(String(20), index=True)
    sku = Column(String(100), index=True)
    disposition = Column(String(30))
    reason = Column(String(120))
    quantity = Column(Integer)
    fc = Column(String(20))
    raw = Column(JSON)

class FbaRemoval(Base):
    __tablename__ = "fba_removals"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("seller_accounts.id"), index=True, nullable=False)
    removal_order_id = Column(String(40), index=True)
    order_type = Column(String(30))
    status = Column(String(30))
    request_date = Column(DateTime, index=True)
    shipped_date = Column(DateTime)
    received_date = Column(DateTime)
    asin = Column(String(20), index=True)
    sku = Column(String(100), index=True)
    quantity = Column(Integer)
    disposition = Column(String(30))
    raw = Column(JSON)

class FbaInventoryAdjustment(Base):
    __tablename__ = "fba_inventory_adjustments"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("seller_accounts.id"), index=True, nullable=False)
    adjustment_date = Column(DateTime, index=True)
    asin = Column(String(20), index=True)
    sku = Column(String(100), index=True)
    quantity = Column(Integer)
    reason = Column(String(40), index=True)  # z.B. Lost_Warehouse, Damaged_Warehouse, Found...
    fc = Column(String(20))
    raw = Column(JSON)

class FbaReimbursement(Base):
    __tablename__ = "fba_reimbursements"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("seller_accounts.id"), index=True, nullable=False)
    posted_date = Column(DateTime, index=True)
    case_id = Column(String(40), index=True)
    asin = Column(String(20), index=True)
    sku = Column(String(100), index=True)
    quantity = Column(Integer)
    amount = Column(Numeric(12,2))
    currency = Column(String(3))
    reason = Column(String(120))
    raw = Column(JSON)
