# build_site.py
# Orchestriert: Scrape -> Normalize -> Report(All) und baut eine statische Site unter ./site
# Ergebnis: ./site/index.html (fertig für GitHub Pages)

import subprocess, sys, shutil
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
SITE = ROOT / "site"

def run(cmd: list[str]):
    print(f"[RUN] {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=ROOT)
    if res.returncode != 0:
        sys.exit(res.returncode)

def main():
    # 1) Scrape öffentliche Monitor-Seite
    run([sys.executable, "untis_monitor_scrape.py"])
    # 2) Normalisieren
    run([sys.executable, "untis_normalize.py"])
    # 3) HTML-Report (alle Klassen/alle Tage mit Dropdowns)
    run([sys.executable, "untis_report_all.py"])

    # 4) Site-Ordner vorbereiten
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True, exist_ok=True)

    # 5) report_all.html als index.html bereitstellen
    src = ROOT / "report_all.html"
    dst = SITE / "index.html"
    if not src.exists():
        print("FEHLER: report_all.html wurde nicht erzeugt.")
        sys.exit(1)
    shutil.copy2(src, dst)

    # 6) Minimaler robots.txt (optional)
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    print(f"OK. Website gebaut unter: {SITE}")
    print(f"Öffne lokal: {dst}")

if __name__ == "__main__":
    main()
