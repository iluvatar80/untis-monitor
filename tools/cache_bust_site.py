# tools/cache_bust_site.py
import os
import re
import sys
import time
from pathlib import Path


def _get_version() -> str:
    """Return short SHA from CI or timestamp fallback."""
    sha = os.environ.get("GITHUB_SHA", "")[:7]
    if sha:
        return sha
    return time.strftime("%Y%m%d%H%M%S")


def _cache_bust_in_html(html_path: Path, version: str) -> bool:
    """Append/replace ?v=VERSION on known local assets inside HTML.

    We target the normalized outputs referenced by the report page(s):
    - untis_subst_normalized.json
    - untis_subst_normalized.csv

    Any existing ?v=... is replaced with the new version.
    """
    text = html_path.read_text(encoding="utf-8")

    # Match the two filenames with optional existing query and hash tail
    pattern = re.compile(
        r"(?P<base>untis_subst_normalized\.(?:json|csv))(?:\?v=[^\"'#]*)?(?P<tail>(?:#[^\"']*)?)"
    )

    def _repl(m: re.Match) -> str:
        base = m.group("base")
        tail = m.group("tail") or ""
        return f"{base}?v={version}{tail}"

    new_text = pattern.sub(_repl, text)
    if new_text != text:
        html_path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main(site_dir: str = "site") -> int:
    version = _get_version()
    site = Path(site_dir)

    if not site.is_dir():
        print(f"[cache-bust] site dir not found: {site}", file=sys.stderr)
        return 1

    changed_any = False
    # Restrict to report*.html to avoid touching unrelated pages
    for html in site.rglob("*.html"):
        if not html.name.startswith("report"):
            continue
        if _cache_bust_in_html(html, version):
            print(f"[cache-bust] updated {html.relative_to(site)} -> v={version}")
            changed_any = True

    if not changed_any:
        print("[cache-bust] no matches found; nothing changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "site"))
