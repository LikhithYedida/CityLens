"""Build the master metro-by-month table with SQL (DuckDB), then test it.

How it works, the same way dbt does:
  1. Run every model in sql/ in order (01_..., 02_..., ...). Each creates one table.
  2. Run every test in sql/tests/. A test is a query that returns the rows that
     BREAK a rule, so zero rows means the test passed.
  3. Save the two marts and write a coverage report to docs/panel_report.md.

Run:  python -m pipeline.build_panel     (run the source pipelines first)
"""
from pathlib import Path

import duckdb

from pipeline.config import CLEAN_DIR, ROOT
from pipeline.utils import SourceError, log, record_run

SQL_DIR = ROOT / "sql"
MARTS_DIR = ROOT / "data" / "marts"
REPORT_PATH = ROOT / "docs" / "panel_report.md"
SPOTLIGHT = {"35620": "New York", "31080": "Los Angeles", "19820": "Detroit",
             "12420": "Austin", "33100": "Miami", "26420": "Houston"}

COVERAGE_COLS = ["home_value", "rent", "mortgage_rate_30y", "employment", "median_household_income",
                 "permits_units", "net_migration", "rent_to_income", "mortgage_to_income"]


def render(sql: str) -> str:
    return sql.replace("{clean}", CLEAN_DIR.as_posix())


def run_models(con: duckdb.DuckDBPyConnection) -> None:
    for path in sorted(SQL_DIR.glob("*.sql")):
        con.execute(render(path.read_text(encoding="utf-8")))
        log.info("Model %s: done", path.stem)


def run_tests(con: duckdb.DuckDBPyConnection) -> list[str]:
    failed = []
    for path in sorted((SQL_DIR / "tests").glob("*.sql")):
        rows = con.execute(render(path.read_text(encoding="utf-8"))).fetchall()
        if rows:
            failed.append(path.stem)
            log.error("Test FAILED %s: %s failing rows, e.g. %s", path.stem, len(rows), rows[:3])
        else:
            log.info("Test passed %s", path.stem)
    return failed


def write_report(con: duckdb.DuckDBPyConnection, failed: list[str]) -> None:
    n_metros, n_months, first, last = con.execute(
        "SELECT count(DISTINCT cbsa_code), count(DISTINCT date), min(date), max(date) FROM mart_metro_month"
    ).fetchone()
    lines = ["# Master Panel Report", "",
             f"**{n_metros:,} metros by {n_months} months ({first:%b %Y} to {last:%b %Y}).** "
             f"Tests: {'all passed' if not failed else 'FAILED: ' + ', '.join(failed)}.", "",
             "## Coverage", "",
             "Share of metro-months with a value. Low numbers are expected for yearly sources in "
             "months before they're published, and for small metros Zillow doesn't track.", "",
             "| Column | All metros | Metropolitan only |", "|---|---|---|"]
    for col in COVERAGE_COLS:
        all_pct, metro_pct = con.execute(f"""
            SELECT avg(({col} IS NOT NULL)::INT),
                   avg(CASE WHEN cbsa_type = 'Metropolitan' THEN ({col} IS NOT NULL)::INT END)
            FROM mart_metro_month""").fetchone()
        lines.append(f"| {col} | {all_pct:.0%} | {metro_pct:.0%} |")

    absorbed = con.execute("SELECT count(*) FROM stg_zillow_xwalk WHERE absorbed_series").fetchone()[0]
    lines += ["", f"{absorbed} Zillow series were absorbed areas (merged into a bigger metro in 2023) "
              "and were left out of the metro join so no metro is counted twice.", "",
              "## Spot check (latest month)", "",
              "| Metro | Home value | Rent | Rent / income | Mortgage / income | Job growth |",
              "|---|---|---|---|---|---|"]
    for code, name in SPOTLIGHT.items():
        r = con.execute("""SELECT home_value, rent, rent_to_income, mortgage_to_income, job_growth_latest
                           FROM mart_metro_latest WHERE cbsa_code = ?""", [code]).fetchone()
        if r:
            fmt = lambda v, f: "" if v is None else f.format(v)
            lines.append(f"| {name} | {fmt(r[0], '${:,.0f}')} | {fmt(r[1], '${:,.0f}')} | "
                         f"{fmt(r[2], '{:.0%}')} | {fmt(r[3], '{:.0%}')} | {fmt(r[4], '{:+.1%}')} |")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> None:
    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    run_models(con)
    failed = run_tests(con)
    write_report(con, failed)
    for table in ("mart_metro_month", "mart_metro_latest"):
        out = MARTS_DIR / f"{table}.parquet"
        con.execute(f"COPY {table} TO '{out.as_posix()}' (FORMAT PARQUET)")
    rows = con.execute("SELECT count(*) FROM mart_metro_month").fetchone()[0]
    record_run("mart_metro_month", rows, "", status="ok" if not failed else "tests_failed")
    log.info("Saved data/marts/ (%s rows). Report: docs/panel_report.md", f"{rows:,}")
    if failed:
        raise SourceError(f"{len(failed)} data test(s) failed: {', '.join(failed)}")


if __name__ == "__main__":
    run()
