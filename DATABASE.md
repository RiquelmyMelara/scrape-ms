# Database Structure

## Connection

| Property | Value |
|---|---|
| Engine | PostgreSQL 17.4 |
| Instance | `scrape-ms-db` (db.t3.micro, RDS) |
| Host | `scrape-ms-db.czookayesk1r.us-east-1.rds.amazonaws.com` |
| Port | `5432` |
| Database | `scrape_ms` |
| User | `scrape_admin` |

## Table: `sales`

Stores scraped ClickFunnels sales data — one row per purchase per contact
per funnel. Populated by `scrape.py --upload` which upserts from the
per-funnel CSVs.

### Columns

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | `SERIAL` | NO | Auto-incrementing primary key |
| `order_id` | `TEXT` | YES | ClickFunnels order identifier |
| `date` | `TEXT` | YES | Sale date as shown on the contact_purchases page |
| `purchase_timestamp` | `TEXT` | YES | Precise timestamp from the contact profile (e.g. `2025-01-26 22:56:45 -0500`). Filled by `--enrich` |
| `customer_name` | `TEXT` | YES | Contact's full name (from profile header during `--enrich`) |
| `email` | `TEXT` | YES | Contact's email address |
| `product` | `TEXT` | YES | Product or offer purchased |
| `amount` | `TEXT` | YES | Purchase amount (numeric string, e.g. `19.00`) |
| `currency` | `TEXT` | YES | Currency symbol if present (e.g. `$`) |
| `status` | `TEXT` | YES | Payment status (`PAID`, `FAILED`, etc.) |
| `contact_id` | `TEXT` | YES | ClickFunnels contact profile ID (numeric string) |
| `funnel_id` | `TEXT` | YES | ClickFunnels funnel ID (numeric string) |
| `funnel_name` | `TEXT` | YES | Human-readable funnel name |

### Indexes

| Index | Type | Columns |
|---|---|---|
| `sales_pkey` | Primary Key (btree) | `id` |
| `sales_contact_id_funnel_id_product_amount_date_key` | Unique (btree) | `contact_id, funnel_id, product, amount, date` |

### Upsert behavior

The `--upload` step uses `INSERT ... ON CONFLICT` on the unique constraint
`(contact_id, funnel_id, product, amount, date)`. On conflict it updates:
`order_id`, `purchase_timestamp`, `customer_name`, `email`, `currency`,
`status`, `funnel_name`.

This means re-running `--upload` after `--enrich` safely backfills
timestamps and names without creating duplicates.

### Example queries

```sql
-- Total sales by funnel
SELECT funnel_name, COUNT(*) AS sales, SUM(amount::numeric) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY funnel_name
ORDER BY revenue DESC;

-- All purchases for a specific contact
SELECT * FROM sales
WHERE email = 'someone@example.com'
ORDER BY purchase_timestamp DESC;

-- Paid sales with timestamps (enriched rows only)
SELECT customer_name, email, product, amount, purchase_timestamp, funnel_name
FROM sales
WHERE status = 'PAID' AND purchase_timestamp IS NOT NULL
ORDER BY purchase_timestamp DESC;

-- Sales count by month
SELECT DATE_TRUNC('month', purchase_timestamp::timestamp) AS month, COUNT(*)
FROM sales
WHERE purchase_timestamp IS NOT NULL
GROUP BY month
ORDER BY month DESC;
```
