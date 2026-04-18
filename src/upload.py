"""Upload scraped sales data to PostgreSQL."""

import csv

import psycopg2
from psycopg2.extras import execute_values

from . import config

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sales (
    id              SERIAL PRIMARY KEY,
    order_id        TEXT,
    date            TEXT,
    purchase_timestamp TEXT,
    customer_name   TEXT,
    email           TEXT,
    product         TEXT,
    amount          TEXT,
    currency        TEXT,
    status          TEXT,
    contact_id      TEXT,
    funnel_id       TEXT,
    funnel_name     TEXT,
    UNIQUE (contact_id, funnel_id, product, amount, date)
);
"""

# Column order must match SALES_FIELDS (minus the auto-generated id)
INSERT_COLS = config.SALES_FIELDS
INSERT_SQL = f"""
INSERT INTO sales ({', '.join(INSERT_COLS)})
VALUES %s
ON CONFLICT (contact_id, funnel_id, product, amount, date) DO UPDATE SET
    order_id           = EXCLUDED.order_id,
    purchase_timestamp = EXCLUDED.purchase_timestamp,
    customer_name      = EXCLUDED.customer_name,
    email              = EXCLUDED.email,
    currency           = EXCLUDED.currency,
    status             = EXCLUDED.status,
    funnel_name        = EXCLUDED.funnel_name
"""


def get_connection():
    if not config.DB_HOST:
        raise RuntimeError("DB_HOST not set in .env — cannot upload")
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE)
    conn.commit()


def upload_all_csvs() -> int:
    """Read every per-funnel CSV and upsert into the sales table. Returns total rows upserted."""
    conn = get_connection()
    try:
        ensure_table(conn)
        total = 0

        for csv_path in sorted(config.OUTPUT_DIR.glob("*.csv")):
            if csv_path.name == config.COMBINED_CSV.name or csv_path.name.startswith("_"):
                continue
            count = _upload_csv(conn, csv_path)
            total += count

        print(f"[upload] total: {total} rows upserted")
        return total
    finally:
        conn.close()


def _upload_csv(conn, csv_path) -> int:
    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return 0

    values = []
    for row in rows:
        values.append(tuple(row.get(col, "") or "" for col in INSERT_COLS))

    with conn.cursor() as cur:
        execute_values(cur, INSERT_SQL, values, page_size=500)
    conn.commit()

    print(f"  [{csv_path.stem}] {len(values)} rows")
    return len(values)
