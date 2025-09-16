# build_site.py
# Baut ./site und veröffentlicht zusätzlich Debug-/Daten-Dateien.

import subprocess, sys, shutil, json
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
SITE = ROOT / "site"

def run(cmd: list[str]):
    print(f"[RUN] {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=ROOT)
    if res.returncode != 0:
        sys.exit(res.returncode)

def main():
    # 1) Scrape
    run([sys.executable, "untis_monitor_scrape.py"])
    # 2) Normalize
    run([sys.executable, "untis_normalize.py"])
    # 3) Report (All)
    run([sys.executable, "untis_report_all.py"])

    # 4) Site-Ordner neu aufbauen
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True, exist_ok=True)

    # 5) report_all.html -> index.html
    src = ROOT / "report_all.html"
    dst = SITE / "index.html"
    if not src.exists():
        print("FEHLER: report_all.html wurde nicht erzeugt.")
        sys.exit(1)
    shutil.copy2(src, dst)

    # 6) Debug-/Daten-Dateien mitschieben
    for name in ["webuntis_subst.json", "untis_subst_normalized.json", "webuntis_subst.csv"]:
        p = ROOT / name
        if p.exists():
            shutil.copy2(p, SITE / name)

    # 6b) debug_meta.json erzeugen (aus webuntis_subst.json)
    meta_src = ROOT / "webuntis_subst.json"
    if meta_src.exists():
        try:
            meta = json.loads(meta_src.read_text(encoding="utf-8")).get("meta", {})
            (SITE / "debug_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("[WARN] Konnte debug_meta.json nicht schreiben:", e)

    # 7) robots.txt
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    # 8) Inhalt von ./site ausgeben (für Logs)
    print("[SITE CONTENTS]")
    for p in sorted(SITE.rglob("*")):
        print("-", p.relative_to(SITE))

    print("OK. Website gebaut:", SITE)

if __name__ == "__main__":
    main()
