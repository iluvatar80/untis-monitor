# untis_monitor_scrape.py
# Zweck: Öffnet die öffentliche WebUntis-Monitor-Seite per Headless-Browser, extrahiert Tabellen
# und speichert die Daten als CSV/JSON + Roh-HTML. Robust gegen doppelte Spaltennamen.

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import json
from datetime import datetime
import pathlib

URL = "https://nessa.webuntis.com/WebUntis/monitor?school=Barmstedt%20Schule&monitorType=subst&format=Homepage"

OUTPUT_CSV = "webuntis_subst.csv"
OUTPUT_JSON = "webuntis_subst.json"
RAW_HTML = "webuntis_subst_raw.html"


def _uniq_headers(headers):
    """Sorgt für eindeutige Spaltennamen innerhalb EINER Tabelle."""
    out, seen = [], {}
    for i, h in enumerate(headers):
        name = (h or "").strip() or f"col_{i+1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def extract_tables(html: str):
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    frames = []

    for ti, table in enumerate(tables):
        # Header ermitteln
        headers = []
        thead = table.find("thead")
        if thead:
            headers = [h.get_text(strip=True) for h in thead.find_all(["th", "td"])]

        rows = table.find_all("tr")
        start_idx = 0
        if not headers and rows:
            # evtl. erste Zeile als Header verwenden, wenn THs vorhanden sind
            ths = rows[0].find_all("th")
            if ths:
                headers = [th.get_text(strip=True) for th in ths]
                start_idx = 1

        # Datenzeilen sammeln
        data_rows = []
        for r in rows[start_idx:]:
            cells = r.find_all(["td", "th"])
            if not cells:
                continue
            row = [c.get_text(separator=" ", strip=True) for c in cells]
            if any(cell for cell in row):
                data_rows.append(row)

        maxlen = max((len(r) for r in data_rows), default=0)
        if maxlen == 0:
            continue

        # Header auf Spaltenzahl bringen und eindeutig machen
        if not headers or len(headers) != maxlen:
            headers = [f"col_{i+1}" for i in range(maxlen)]
        headers = _uniq_headers(headers)

        # Zeilen auf Spaltenzahl auffüllen
        normalized = [r + [""] * (maxlen - len(r)) for r in data_rows]

        df = pd.DataFrame(normalized, columns=headers)
        df.insert(0, "table_index", ti)

        # WICHTIG: auch hier sicherstellen, dass df.columns eindeutig sind
        df.columns = _uniq_headers(list(df.columns))

        frames.append(df)

    return frames


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        # etwas mehr Zeit geben, damit JS die Tabellen baut
        page.wait_for_timeout(4000)
        try:
            page.wait_for_selector("table", timeout=8000)
        except Exception:
            pass
        html = page.content()
        browser.close()

    # Roh-HTML speichern
    pathlib.Path(RAW_HTML).write_text(html, encoding="utf-8")

    frames = extract_tables(html)
    meta = {
        "url": URL,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "tables_found": len(frames),
    }

    if frames:
        # Alle Tabellen gemeinsam exportieren (outer-Join auf Spalten)
        # Da jede Tabelle intern eindeutige Spalten hat, ist concat jetzt stabil.
        df_all = pd.concat(frames, ignore_index=True, join="outer")
        df_all.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

        json_obj = {
            "meta": meta,
            "tables": {
                str(i): frames[i].to_dict(orient="records") for i in range(len(frames))
            },
            "combined": df_all.to_dict(orient="records"),
        }
    else:
        # Fallback: Textblöcke sammeln, falls keine Tabellen gefunden wurden
        soup = BeautifulSoup(html, "lxml")
        items = [
            el.get_text(" ", strip=True)
            for el in soup.select("div, li, p")
            if el.get_text(strip=True)
        ]
        json_obj = {
            "meta": {**meta, "note": "no tables found, raw text extracted"},
            "text_blocks": items[:500],
        }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_obj, f, ensure_ascii=False, indent=2)

    print(f"Fertig. Meta: {meta}")


if __name__ == "__main__":
    main()
