"""Offline report with task switching and state/event replay; no network assets."""
import json
from pathlib import Path


def write_report(results, path):
    data = json.dumps(results, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("report_template.html").read_text(encoding="utf-8")
    Path(path).write_text(template.replace("__REPORT_DATA__", data), encoding="utf-8")
