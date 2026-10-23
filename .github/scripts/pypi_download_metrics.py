#!/usr/bin/env python3
"""Collect daily PyPI download metrics for ros-mcp.

Data source: the public ClickHouse PyPI dataset (https://sql-clickhouse.clickhouse.com,
user "demo", no password). It mirrors the official BigQuery table
bigquery-public-data.pypi.file_downloads, one row per downloaded file.

Writes two CSVs in the metrics-branch format (one row per key, `last_updated` last):

- daily_pypi_downloads.csv: date, version, system, installer, ci, downloads
- daily_pypi_downloads_summary.csv: date, total, user installs, CI, mirrors, other

Each run re-fetches a window of complete UTC days (today is partial and skipped) and
replaces those dates in the CSVs, so re-runs are safe.

Usage:
    python .github/scripts/pypi_download_metrics.py --out .metrics            # last 7 days
    python .github/scripts/pypi_download_metrics.py --out .metrics --start 2025-09-01
"""

import argparse
import csv
import json
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

CLICKHOUSE_URL = "https://sql-clickhouse.clickhouse.com/"
CLICKHOUSE_USER = "demo"

DETAIL_FILE = "daily_pypi_downloads.csv"
SUMMARY_FILE = "daily_pypi_downloads_summary.csv"
DETAIL_FIELDS = ["date", "version", "system", "installer", "ci", "downloads", "last_updated"]
SUMMARY_FIELDS = [
    "date",
    "total_downloads",
    "user_installs",
    "ci_downloads",
    "mirror_downloads",
    "other_downloads",
    "last_updated",
]

# Installers that a person (or an MCP client running `uvx`) uses to install a package.
USER_INSTALLERS = {"pip", "uv", "poetry", "pdm", "pipenv", "pex"}
# Tools that copy whole indexes; their downloads say nothing about users.
MIRROR_INSTALLERS = {"bandersnatch", "Nexus", "Artifactory", "devpi", "z3c.pypimirror"}

DETAIL_QUERY = """
SELECT
    date,
    version,
    system,
    installer,
    toString(ci) AS ci,
    count() AS downloads
FROM pypi.pypi
WHERE project = {project:String}
  AND date >= {start:Date}
  AND date <= {end:Date}
GROUP BY date, version, system, installer, ci
ORDER BY date, version, system, installer, ci
FORMAT JSONEachRow
"""

# Freshness check: the newest day loaded for a very popular project. A scan across all
# projects would exceed the demo user's row limit.
FRESHNESS_PROJECT = "requests"
MAX_DATE_QUERY = """
SELECT max(date) AS max_date
FROM pypi.pypi
WHERE project = {project:String} AND date >= today() - 7
FORMAT JSONEachRow
"""

# The demo user may return at most 10,000 result rows, so fetch long ranges in chunks.
CHUNK_DAYS = 31


def run_query(query: str, params: dict[str, str], retries: int = 3) -> list[dict]:
    """Run a parameterized ClickHouse query and return the JSONEachRow rows."""
    # The demo user's default read_overflow_mode is "break", which silently returns
    # partial results when a query reads too many rows. "throw" turns that into an error.
    qs = {"user": CLICKHOUSE_USER, "read_overflow_mode": "throw"}
    qs.update({f"param_{k}": v for k, v in params.items()})
    url = CLICKHOUSE_URL + "?" + urllib.parse.urlencode(qs)
    request = urllib.request.Request(
        url,
        data=query.encode("utf-8"),
        headers={"User-Agent": "ros-mcp-server-metrics"},
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
            return [json.loads(line) for line in body.splitlines() if line.strip()]
        except Exception as e:
            if attempt == retries:
                raise RuntimeError(f"ClickHouse query failed after {retries} attempts: {e}") from e
            print(f"[metrics] query attempt {attempt} failed ({e}); retrying", file=sys.stderr)
            time.sleep(5 * attempt)
    return []


def classify(installer: str, ci: str) -> str:
    """Return the summary bucket for one download: user, ci, mirror or other."""
    if ci == "true":
        return "ci"
    if installer in USER_INSTALLERS:
        return "user"
    if installer in MIRROR_INSTALLERS:
        return "mirror"
    return "other"


def normalize(rows: list[dict], last_updated: str) -> list[dict]:
    """Turn query rows into detail CSV rows; empty fields become 'unknown'."""
    out = []
    for r in rows:
        out.append(
            {
                "date": r["date"],
                "version": r["version"] or "unknown",
                "system": r["system"] or "unknown",
                "installer": r["installer"] or "unknown",
                "ci": r["ci"] or "unknown",
                "downloads": str(int(r["downloads"])),
                "last_updated": last_updated,
            }
        )
    return out


def summarize(detail_rows: list[dict], days: list[str], last_updated: str) -> list[dict]:
    """Build one summary row per day; days without downloads get zeros."""
    totals = {d: defaultdict(int) for d in days}
    for r in detail_rows:
        bucket = classify(r["installer"], r["ci"])
        n = int(r["downloads"])
        totals[r["date"]][bucket] += n
        totals[r["date"]]["total"] += n
    return [
        {
            "date": d,
            "total_downloads": str(t["total"]),
            "user_installs": str(t["user"]),
            "ci_downloads": str(t["ci"]),
            "mirror_downloads": str(t["mirror"]),
            "other_downloads": str(t["other"]),
            "last_updated": last_updated,
        }
        for d, t in totals.items()
    ]


def merge_rows(existing: list[dict], new: list[dict], days: set[str]) -> list[dict]:
    """Replace every existing row whose date is in `days` with the new rows."""
    kept = [r for r in existing if r["date"] not in days]
    keys = ("date", "version", "system", "installer", "ci")
    return sorted(kept + new, key=lambda r: tuple(r.get(k, "") for k in keys))


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv_atomic(path: str, fields: list[str], rows: list[dict]) -> None:
    """Write to a temp file in the same folder, then rename over the target."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows({k: r[k] for k in fields} for r in rows)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def date_range(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True, help="Folder for the CSV files (e.g. .metrics)")
    parser.add_argument("--project", default="ros-mcp", help="PyPI project name")
    parser.add_argument("--days", type=int, default=7, help="Complete days to re-fetch")
    parser.add_argument("--start", help="Backfill from this date (YYYY-MM-DD); overrides --days")
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    start = date.fromisoformat(args.start) if args.start else today - timedelta(days=args.days)

    # The dataset updates during the day, so only fetch days it has fully loaded.
    max_rows = run_query(MAX_DATE_QUERY, {"project": FRESHNESS_PROJECT})
    if not max_rows or max_rows[0]["max_date"] in ("", "1970-01-01"):
        raise RuntimeError("Dataset has no data for the last 7 days; refusing to write zeros")
    dataset_max = date.fromisoformat(max_rows[0]["max_date"])
    end = min(today - timedelta(days=1), dataset_max - timedelta(days=1))
    if end < start:
        print(f"[metrics] no complete days between {start} and {end}; nothing to do")
        return 0

    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS - 1), end)
        rows += run_query(
            DETAIL_QUERY,
            {
                "project": args.project,
                "start": chunk_start.isoformat(),
                "end": chunk_end.isoformat(),
            },
        )
        chunk_start = chunk_end + timedelta(days=1)
    days = date_range(start, end)
    detail = normalize(rows, last_updated)
    summary = summarize(detail, days, last_updated)

    os.makedirs(args.out, exist_ok=True)
    detail_path = os.path.join(args.out, DETAIL_FILE)
    summary_path = os.path.join(args.out, SUMMARY_FILE)
    day_set = set(days)
    write_csv_atomic(detail_path, DETAIL_FIELDS, merge_rows(read_csv(detail_path), detail, day_set))
    write_csv_atomic(
        summary_path, SUMMARY_FIELDS, merge_rows(read_csv(summary_path), summary, day_set)
    )

    total = sum(int(r["downloads"]) for r in detail)
    users = sum(int(r["user_installs"]) for r in summary)
    print(f"[metrics] {args.project} {start}..{end}: {total} downloads, {users} user installs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
