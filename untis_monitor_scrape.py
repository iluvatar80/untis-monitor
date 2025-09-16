# untis_monitor_scrape.py
# Wartet zuverlässig, bis beide Tagesblöcke gerendert sind (>= 8 Tabellen),
# setzt de-DE/Europe/Berlin und scrollt, falls lazy load.

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import json, re, time
from datetime import datetime
import pathlib

URL = "https://nessa.webuntis.com/WebUntis/monitor?school=Barmstedt%20Schule&monitorType=subst&format=Homepage"

OUTPUT_CSV = "webuntis_subst.csv"
OUTPUT_JSON = "webuntis_subst.json"
RAW_HTML = "webuntis_subst_raw.html"

def _uniq_headers(headers):
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
        headers = []
        thead = table.find("thead")
        if thead:
            headers = [h.get_text(strip=True) for h in thead.find_all(["th", "td"])]
        rows = table.find_all("tr")
        start_idx = 0
        if not headers and rows:
            ths = rows[0].find_all("th")
            if ths:
                headers = [th.get_text(strip=True) for th in ths]
                start_idx = 1
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
        if not headers or len(headers) != maxlen:
            headers = [f"col_{i+1}" for i in range(maxlen)]
        headers = _uniq_headers(headers)
        normalized = [r + [""] * (maxlen - len(r)) for r in data_rows]
        df = pd.DataFrame(normalized, columns=headers)
        df.insert(0, "table_index", ti)
        df.columns = _uniq_headers(list(df.columns))
        frames.append(df)
    return frames

def _wait_until_ready(page, min_tables=8, hard_timeout_ms=60000):
    """Wartet bis mind. min_tables <table>-Elemente existieren. Scrollt, falls lazy load."""
    deadline = time.time() + hard_timeout_ms/1000
    last_count = -1
    while time.time() < deadline:
        try:
            count = page.locator("table").count()
        except Exception:
            count = 0
        if count >= min_tables:
            break
        # Scroll an das Ende/Anfang um lazy rendering zu triggern
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(600)
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass
        if count != last_count:
            last_count = count
        page.wait_for_timeout(700)
    html = page.content()
    # Header-Zeilen zählen (optional, Diagnose)
    headers_found = len(re.findall(
        r'>\s*Stunde\s*<.*?>\s*Klassen\s*<.*?>\s*Fach\s*<.*?>\s*Lehrkraft\s*<.*?>\s*Vertretungstext\s*<',
        html, flags=re.S | re.I))
    return html, count, headers_found

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="de-DE",
            timezone_id="Europe/Berlin",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(3000)
        html, table_count, headers_found = _wait_until_ready(page, min_tables=8, hard_timeout_ms=60000)
        context.close()
        browser.close()

    pathlib.Path(RAW_HTML).write_text(html, encoding="utf-8")

    frames = extract_tables(html)
    meta = {
        "url": URL,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "tables_found": len(frames),
        "tables_in_dom": table_count,
        "headers_found": headers_found,
        "locale": "de-DE",
        "timezone": "Europe/Berlin",
    }

    if frames:
        df_all = pd.concat(frames, ignore_index=True, join="outer")
        df_all.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        json_obj = {
            "meta": meta,
            "tables": {str(i): frames[i].to_dict(orient="records") for i in range(len(frames))},
            "combined": df_all.to_dict(orient="records"),
        }
    else:
        soup = BeautifulSoup(html, "lxml")
        items = [el.get_text(" ", strip=True) for el in soup.select("div, li, p") if el.get_text(strip=True)]
        json_obj = {"meta": {**meta, "note": "no tables found, raw text extracted"}, "text_blocks": items[:500]}

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_obj, f, ensure_ascii=False, indent=2)

    print(f"Fertig. Meta: {meta}")

if __name__ == "__main__":
    main()
