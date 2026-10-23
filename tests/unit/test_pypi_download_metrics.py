"""Unit tests for .github/scripts/pypi_download_metrics.py (no network)."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "pypi_download_metrics.py"
_spec = importlib.util.spec_from_file_location("pypi_download_metrics", SCRIPT)
metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metrics)

TS = "2026-10-22 00:00:00 UTC"


def _row(day, installer, ci="false", downloads=1, version="3.1.2", system="Linux"):
    return {
        "date": day,
        "version": version,
        "system": system,
        "installer": installer,
        "ci": ci,
        "downloads": str(downloads),
    }


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


class TestClassify:
    def test_user_installers(self):
        assert metrics.classify("uv", "false") == "user"
        assert metrics.classify("pip", "unknown") == "user"

    def test_ci_wins_over_installer(self):
        assert metrics.classify("uv", "true") == "ci"

    def test_mirror(self):
        assert metrics.classify("bandersnatch", "false") == "mirror"

    def test_other(self):
        assert metrics.classify("Browser", "false") == "other"
        assert metrics.classify("unknown", "false") == "other"


# ---------------------------------------------------------------------------
# normalize / summarize
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_empty_fields_become_unknown(self):
        rows = metrics.normalize([_row("2026-10-20", "", system="")], TS)
        assert rows[0]["installer"] == "unknown"
        assert rows[0]["system"] == "unknown"
        assert rows[0]["last_updated"] == TS


class TestSummarize:
    def test_buckets_add_up_to_total(self):
        detail = metrics.normalize(
            [
                _row("2026-10-20", "uv", downloads=5),
                _row("2026-10-20", "pip", ci="true", downloads=2),
                _row("2026-10-20", "bandersnatch", downloads=3),
                _row("2026-10-20", "", downloads=1),
            ],
            TS,
        )
        (day,) = metrics.summarize(detail, ["2026-10-20"], TS)
        assert day["total_downloads"] == "11"
        assert day["user_installs"] == "5"
        assert day["ci_downloads"] == "2"
        assert day["mirror_downloads"] == "3"
        assert day["other_downloads"] == "1"

    def test_days_without_downloads_get_zero_rows(self):
        rows = metrics.summarize([], ["2026-10-20", "2026-10-21"], TS)
        assert [r["date"] for r in rows] == ["2026-10-20", "2026-10-21"]
        assert all(r["total_downloads"] == "0" for r in rows)


# ---------------------------------------------------------------------------
# merge_rows / CSV round trip
# ---------------------------------------------------------------------------


class TestMerge:
    def test_refetched_days_are_replaced_others_kept(self):
        old = metrics.normalize(
            [_row("2026-10-19", "uv", downloads=4), _row("2026-10-20", "uv", downloads=1)],
            "old",
        )
        new = metrics.normalize([_row("2026-10-20", "uv", downloads=9)], TS)
        merged = metrics.merge_rows(old, new, {"2026-10-20"})
        assert [(r["date"], r["downloads"], r["last_updated"]) for r in merged] == [
            ("2026-10-19", "4", "old"),
            ("2026-10-20", "9", TS),
        ]

    def test_csv_round_trip_is_stable(self, tmp_path):
        path = str(tmp_path / metrics.DETAIL_FILE)
        rows = metrics.normalize([_row("2026-10-20", "uv", downloads=3)], TS)
        metrics.write_csv_atomic(path, metrics.DETAIL_FIELDS, rows)
        assert metrics.read_csv(path) == rows
        assert list(tmp_path.iterdir()) == [tmp_path / metrics.DETAIL_FILE]
