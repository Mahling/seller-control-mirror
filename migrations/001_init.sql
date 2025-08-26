-- Initial schema for Seller-Control (Multi-Account)
CREATE TABLE IF NOT EXISTS seller_accounts (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  region VARCHAR(10) DEFAULT 'eu',
  marketplaces VARCHAR(200) DEFAULT 'DE,FR,IT,ES',
  refresh_token TEXT NOT NULL,
  lwa_client_id VARCHAR(200),
  lwa_client_secret VARCHAR(200),
  aws_access_key VARCHAR(200),
  aws_secret_key VARCHAR(200),
  role_arn VARCHAR(300),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  order_id VARCHAR(40),
  purchase_date TIMESTAMP,
  status VARCHAR(40),
  marketplace VARCHAR(10),
  data JSONB
);

CREATE TABLE IF NOT EXISTS order_items (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  order_id VARCHAR(40),
  asin VARCHAR(20),
  sku VARCHAR(80),
  qty INTEGER,
  price_amount NUMERIC(12,2),
  currency VARCHAR(3)
);

CREATE TABLE IF NOT EXISTS returns_fba (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  return_date TIMESTAMP,
  asin VARCHAR(20),
  sku VARCHAR(80),
  disposition VARCHAR(30),
  reason VARCHAR(200),
  fc VARCHAR(20),
  qty INTEGER
);

CREATE TABLE IF NOT EXISTS returns_fbm (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  return_date TIMESTAMP,
  asin VARCHAR(20),
  sku VARCHAR(80),
  reason VARCHAR(200),
  qty INTEGER
);

CREATE TABLE IF NOT EXISTS removals_orders (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  removal_order_id VARCHAR(50),
  order_type VARCHAR(20),
  status VARCHAR(30),
  created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS removals_shipments (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  removal_order_id VARCHAR(50),
  tracking VARCHAR(60),
  qty INTEGER,
  received_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inventory_ledger (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  event_date TIMESTAMP,
  event_type VARCHAR(40),
  asin VARCHAR(20),
  sku VARCHAR(80),
  fc VARCHAR(20),
  qty INTEGER,
  reference VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS reimbursements (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  posted_date TIMESTAMP,
  asin VARCHAR(20),
  sku VARCHAR(80),
  case_id VARCHAR(60),
  reason VARCHAR(200),
  units INTEGER,
  amount NUMERIC(12,2)
);

CREATE TABLE IF NOT EXISTS recon_results (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES seller_accounts(id),
  asin VARCHAR(20),
  sku VARCHAR(80),
  window_from TIMESTAMP,
  window_to TIMESTAMP,
  lost_units INTEGER DEFAULT 0,
  damaged_units INTEGER DEFAULT 0,
  found_units INTEGER DEFAULT 0,
  reimbursed_units INTEGER DEFAULT 0,
  reimbursed_amount NUMERIC(12,2) DEFAULT 0,
  open_units INTEGER DEFAULT 0,
  open_amount NUMERIC(12,2) DEFAULT 0
);
