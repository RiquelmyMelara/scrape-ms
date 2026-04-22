import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
LOGIN_URL = os.getenv("LOGIN_URL", "https://app.clickfunnels.com/users/sign_in")

CDP_URL = os.getenv("CDP_URL", "http://localhost:9222")
BASE_URL = "https://app.clickfunnels.com"
FUNNELS_URL = f"{BASE_URL}/funnels"

# Database (PostgreSQL)
DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "scrape_ms")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

OUTPUT_DIR = ROOT / "output"
STATE_FILE = OUTPUT_DIR / "_state.json"
ENRICH_STATE_FILE = OUTPUT_DIR / "_enrich_state.json"
UPLOAD_STATE_FILE = OUTPUT_DIR / "_upload_state.json"
FUNNELS_FILE = OUTPUT_DIR / "funnels.json"
COMBINED_CSV = OUTPUT_DIR / "sales_all.csv"
BLACKLIST_CSV = OUTPUT_DIR / "blacklist.csv"

# Names that get moved to the blacklist by --clean (case-insensitive substring match)
BLACKLIST_NAMES = [
    "glenn", "luis", "frank", "test", "spam",
    "mitch", "statbrook", "katherine", "paul", "sean",
]

SALES_FIELDS = [
    "order_id",
    "date",
    "purchase_timestamp",  # filled by --enrich from contact profile
    "customer_name",
    "email",
    "product",
    "amount",
    "currency",
    "status",
    "contact_id",
    "funnel_id",
    "funnel_name",
]
