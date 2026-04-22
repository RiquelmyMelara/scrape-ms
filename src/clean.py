"""Clean step: move rows matching blacklisted names out of per-funnel CSVs.

Blacklisted rows go to output/blacklist.csv for manual review. They can be
added back by removing them from blacklist.csv and re-running --sales or
editing the per-funnel CSV directly.
"""

import csv

from . import config


def clean_csvs(funnel_id: str | None = None) -> tuple[int, int]:
    """Remove blacklisted rows from CSVs. Returns (kept, blacklisted) counts."""
    # Load existing blacklist so we append rather than overwrite
    existing_bl = _load_blacklist()

    total_kept = 0
    total_bl = 0

    if funnel_id:
        csv_path = config.OUTPUT_DIR / f"{funnel_id}.csv"
        if csv_path.exists():
            k, b = _clean_csv(csv_path, existing_bl)
            total_kept += k
            total_bl += b
    else:
        for csv_path in sorted(config.OUTPUT_DIR.glob("*.csv")):
            if csv_path.name in (
                config.COMBINED_CSV.name,
                config.BLACKLIST_CSV.name,
            ) or csv_path.name.startswith("_"):
                continue
            k, b = _clean_csv(csv_path, existing_bl)
            total_kept += k
            total_bl += b

    # Write accumulated blacklist
    _save_blacklist(existing_bl)

    print(f"[clean] kept {total_kept} rows, blacklisted {total_bl} "
          f"(total in blacklist: {len(existing_bl)})")
    return total_kept, total_bl


def _clean_csv(csv_path, blacklist: list[dict]) -> tuple[int, int]:
    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return 0, 0

    keep = []
    removed = 0
    for row in rows:
        if _is_blacklisted(row):
            blacklist.append(row)
            removed += 1
        else:
            keep.append(row)

    if removed:
        # Rewrite the CSV without blacklisted rows
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=config.SALES_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(keep)
        print(f"  [{csv_path.stem}] {len(keep)} kept, {removed} blacklisted")
    else:
        print(f"  [{csv_path.stem}] {len(keep)} kept (clean)")

    return len(keep), removed


def _is_blacklisted(row: dict) -> bool:
    name = (row.get("customer_name") or "").lower()
    email = (row.get("email") or "").lower()
    text = f"{name} {email}"
    return any(bl in text for bl in config.BLACKLIST_NAMES)


def _load_blacklist() -> list[dict]:
    if not config.BLACKLIST_CSV.exists():
        return []
    with config.BLACKLIST_CSV.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save_blacklist(rows: list[dict]) -> None:
    with config.BLACKLIST_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=config.SALES_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
