# build_site.py
# Baut ./site für GitHub Pages:
# 1) Scrape (untis_monitor_scrape.py)
# 2) Normalize (untis_normalize.py)
# 3) Report (untis_report_all.py)
# 4) Kopiert index + Debug-/Daten-Dateien nach ./site
# 5) Listet den Inhalt von ./site für die CI-Logs

from pathlib import Path
import subprocess
import sys
import shutil
import json
from datetime import datetime

ROOT = Path(__file__).parent.resolve()
SITE = ROOT / "site"

def run(cmd: list[str]) -> None:
    print(f"[RUN] {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=ROOT)
    if res.returncode != 0:
        print(f"[ERROR] Command failed with exit code {res.returncode}: {' '.join(cmd)}")
        sys.exit(res.returncode)

def main() -> None:
    print(f"[INFO] Build start: {datetime.now().isoformat(timespec='seconds')}")
    print(f"[INFO] Python: {sys.executable}")
    print(f"[INFO] Project root: {ROOT}")

    # 1) Scrape -> erzeugt u. a. webuntis_subst.json / raw_*.html
    run([sys.executable, "untis_monitor_scrape.py"])

    # 2) Normalisieren -> erzeugt untis_subst_normalized.json
    run([sys.executable, "untis_normalize.py"])

    # 3) Report (alle Klassen/Tage) -> erzeugt report_all.html
    run([sys.executable, "untis_report_all.py"])

    # 4) site/ neu aufbauen
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True, exist_ok=True)

    # 5) report_all.html als index.html veröffentlichen
    src_report = ROOT / "report_all.html"
    dst_index = SITE / "index.html"
    if not src_report.exists():
        print("[ERROR] report_all.html wurde nicht erzeugt – Abbruch.")
        sys.exit(1)
    shutil.copy2(src_report, dst_index)

    # 6) Debug-/Daten-Artefakte mitveröffentlichen (falls vorhanden)
    publish_files = [
        "webuntis_subst.json",
        "untis_subst_normalized.json",
        "webuntis_subst.csv",
        "webuntis_subst_raw_1.html",
        "webuntis_subst_raw_2.html",
    ]
    for name in publish_files:
        p = ROOT / name
        if p.exists():
            shutil.copy2(p, SITE / name)

    # 6b) kompakte Meta-Datei schreiben (aus webuntis_subst.json)
    meta_src = ROOT / "webuntis_subst.json"
    if meta_src.exists():
        try:
            data = json.loads(meta_src.read_text(encoding="utf-8"))
            meta = data.get("meta", {})
            (SITE / "debug_meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[WARN] debug_meta.json konnte nicht erzeugt werden: {e}")

    # 7) robots.txt minimal
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    # 8) Site-Inhalt für Logs ausgeben
    print("[SITE CONTENTS]")
    for p in sorted(SITE.rglob("*")):
        print("-", p.relative_to(SITE))

    print(f"[INFO] Build done: {SITE}")

if __name__ == "__main__":
    main()
