# tools/inject_header.py
"""
Post-process report HTML to inject a header with:
- Title: "Gottfried-Semper-Schule-Barmstedt Vertretungsplan"
- Timestamp: "Stand: <dd.mm.yyyy HH:MM> <TZ>"

Usage (from repo root):
    python tools/inject_header.py docs
If no directory given, defaults to "site".

Timestamp source (first match wins):
- <dir>/debug_meta.json  keys: "generated_at", "timestamp", "captured_at", "ts"
- mtime of untis_subst_normalized.json / webuntis_subst.json
- current time
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from zoneinfo import ZoneInfo  # Python 3.11+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

TITLE = "Gottfried-Semper-Schule-Barmstedt Vertretungsplan"
HEADER_ID = "report-header"


@dataclass
class Meta:
    dt: datetime
    tz: str


def _parse_any_dt(val: str | int | float, tz: str) -> Optional[datetime]:
    # ISO 8601 string
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo(tz) if ZoneInfo else timezone.utc)
        except Exception:
            pass
    # Epoch seconds
    try:
        sec = float(val)
        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
        return dt.astimezone(ZoneInfo(tz) if ZoneInfo else timezone.utc)
    except Exception:
        return None


def _load_meta_time(dir_path: Path) -> Meta:
    tz = "Europe/Berlin"
    meta_file = dir_path / "debug_meta.json"

    # 1) debug_meta.json
    if meta_file.exists():
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            tz = data.get("timezone") or data.get("tz") or tz
            for key in ("generated_at", "timestamp", "captured_at", "ts"):
                if key in data and data[key] is not None:
                    dt = _parse_any_dt(data[key], tz)
                    if dt:
                        return Meta(dt=dt, tz=tz)
        except Exception:
            pass

    # 2) mtimes of known artifacts
    for name in ("untis_subst_normalized.json", "webuntis_subst.json"):
        p = dir_path / name
        if p.exists():
            try:
                dt = datetime.fromtimestamp(
                    p.stat().st_mtime,
                    tz=ZoneInfo(tz) if ZoneInfo else timezone.utc,
                )
                return Meta(dt=dt, tz=tz)
            except Exception:
                continue

    # 3) now
    now = datetime.now(ZoneInfo(tz) if ZoneInfo else timezone.utc)
    return Meta(dt=now, tz=tz)


def _fmt(meta: Meta) -> str:
    # e.g. 16.09.2025 18:45 CEST
    try:
        tz_abbr = meta.dt.tzname() or meta.tz
    except Exception:
        tz_abbr = meta.tz
    return meta.dt.strftime(f"%d.%m.%Y %H:%M {tz_abbr}")


def _inject_header(html: str, stamp: str) -> str:
    header_html = (
        f"<header id=\"{HEADER_ID}\" style=\"font-family:system-ui,Segoe UI,Arial,sans-serif;"
        "max-width:1200px;margin:16px auto 8px;padding:12px 16px;"
        "display:flex;align-items:baseline;gap:16px;border-bottom:1px solid #ddd;\">"
        f"<h1 style=\"margin:0;font-size:22px;font-weight:600;\">{TITLE}</h1>"
        f"<div style=\"opacity:.75;font-size:14px;\">Stand: {stamp}</div>"
        "</header>"
    )

    if f"id=\"{HEADER_ID}\"" in html:
        # Update timestamp only (callable replacement avoids backrefs)
        def _repl(m: "re.Match[str]") -> str:
            return m.group(1) + stamp
        return re.sub(r"(Stand:\s*)([^<]+)", _repl, html, count=1)

    # Insert right after <body ...>
    m = re.search(r"<body[^>]*>", html, flags=re.IGNORECASE)
    if m:
        i = m.end()
        return html[:i] + "\n" + header_html + "\n" + html[i:]

    # Fallback: prepend
    return header_html + "\n" + html


def main(target_dir: Optional[str] = None) -> int:
    dir_path = Path(target_dir or "site").resolve()
    if not dir_path.is_dir():
        print(f"[inject-header] directory not found: {dir_path}")
        return 1

    stamp = _fmt(_load_meta_time(dir_path))

    changed = False
    for name in ("index.html", "report_all.html"):
        p = dir_path / name
        if p.exists():
            html = p.read_text(encoding="utf-8")
            new_html = _inject_header(html, stamp)
            if new_html != html:
                p.write_text(new_html, encoding="utf-8")
                print(f"[inject-header] updated {name} → Stand: {stamp}")
                changed = True
            else:
                print(f"[inject-header] no change needed for {name}")

    if not changed:
        print("[inject-header] nothing changed")
    return 0


if __name__ == "main":  # safe-guard if run via -m
    sys.exit(main())

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
