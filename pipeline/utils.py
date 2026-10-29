"""Shared helpers: safe downloads and a run log."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

from pipeline.config import ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("citylens")

RUN_LOG = ROOT / "data" / "run_log.jsonl"
HEADERS = {"User-Agent": "citylens-portfolio-project (data research)"}


class SourceError(RuntimeError):
    """Raised when a source is unreachable or returns something unexpected."""


def download(url: str, dest: Path, timeout: int = 120) -> Path:
    """Download a file, failing loudly with a clear fix instead of silently."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise SourceError(f"Could not reach {url}: {exc}") from exc
    if resp.status_code != 200:
        hint = (" Zillow probably changed the download path: copy the new link from "
                "zillow.com/research/data into pipeline/config.py." if "zillow" in url else "")
        raise SourceError(f"{url} returned HTTP {resp.status_code}.{hint}")
    if b"<html" in resp.content[:500].lower():
        raise SourceError(f"{url} returned a web page, not a data file.")
    dest.write_bytes(resp.content)
    log.info("Downloaded %s (%.1f MB)", dest.name, len(resp.content) / 1e6)
    return dest


def record_run(source: str, rows: int, latest_date: str, status: str = "ok", note: str = "") -> None:
    """Append one line per source per run: proof the pipeline is healthy."""
    entry = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "status": status,
        "rows": rows,
        "latest_date": latest_date,
        "note": note,
    }
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
