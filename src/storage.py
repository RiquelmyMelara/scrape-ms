import csv
import json
from pathlib import Path

from . import config


def ensure_output() -> None:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def funnel_csv_path(funnel_id: str) -> Path:
    return config.OUTPUT_DIR / f"{funnel_id}.csv"


def write_rows(funnel_id: str, rows: list[dict]) -> None:
    path = funnel_csv_path(funnel_id)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=config.SALES_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def write_combined() -> int:
    total = 0
    with config.COMBINED_CSV.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=config.SALES_FIELDS, extrasaction="ignore")
        w.writeheader()
        for p in sorted(config.OUTPUT_DIR.glob("*.csv")):
            if p.name == config.COMBINED_CSV.name or p.name.startswith("_"):
                continue
            with p.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    w.writerow(row)
                    total += 1
    return total


def load_state() -> dict:
    if config.STATE_FILE.exists():
        return json.loads(config.STATE_FILE.read_text())
    return {"completed": []}


def save_state(state: dict) -> None:
    config.STATE_FILE.write_text(json.dumps(state, indent=2))


def save_funnels(funnels: list[dict]) -> None:
    config.FUNNELS_FILE.write_text(json.dumps(funnels, indent=2))


def load_funnels() -> list[dict]:
    if not config.FUNNELS_FILE.exists():
        raise FileNotFoundError(
            f"{config.FUNNELS_FILE} not found. Run `scrape.py --funnels` first."
        )
    return json.loads(config.FUNNELS_FILE.read_text())
