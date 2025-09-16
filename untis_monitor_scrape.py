# untis_monitor_scrape.py
# Lädt "heute", versucht dann zum nächsten Slide ("morgen") zu wechseln,
# extrahiert beide Zustände und führt die Tabellen zusammen.
# JSON wird NaN-frei geschrieben.

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import json, re, time, hashlib
from datetime import datetime
from pathlib import Path

URL = "https://nessa.webuntis.com/WebUntis/monitor?school=Barmstedt%20Schule&monitorType=subst&format=Homepage"

OUT_CSV  = "webuntis_subst.csv"
OUT_JSON = "webuntis_subst.json"
RAW1_HTML = "webuntis_subst_raw_1.html"
RAW2_HTML = "webuntis_subst_raw_2.html"  # optional, nur wenn Slide 2 gefunden

# ---------- HTML -> DataFrames ----------
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
        if not data_rows:
            continue
        maxlen = max(len(r) for r in data_rows)
        if not headers or len(headers) != maxlen:
            headers = [f"col_{i+1}" for i in range(maxlen)]
        headers = _uniq_headers(headers)
        normalized = [r + [""] * (maxlen - len(r)) for r in data_rows]
        df = pd.DataFrame(normalized, columns=headers)
        df.insert(0, "table_index", ti)
        df.columns = _uniq_headers(list(df.columns))
        frames.append(df)
    return frames

# ---------- Warten / Slides ----------
def _counts_from_html(html: str):
    tables = len(re.findall(r"<table", html, flags=re.I))
    headers = len(re.findall(
        r'>\s*Stunde\s*<.*?>\s*Klassen\s*<.*?>\s*Fach\s*<.*?>\s*Lehrkraft\s*<.*?>\s*Vertretungstext\s*<',
        html, flags=re.S | re.I))
    return tables, headers

def _wait_ready(page, min_tables=4, min_headers=1, timeout_s=90):
    deadline = time.time() + timeout_s
    html = page.content()
    while time.time() < deadline:
        html = page.content()
        t, h = _counts_from_html(html)
        if t >= min_tables and h >= min_headers:
            break
        page.wait_for_timeout(700)
    return html

def _try_next_slide(page):
    """Versucht, zum 'Morgen'-Slide zu wechseln: Pfeil rechts & gängige Next-Buttons."""
    # 1) Tastatur (viele Slider reagieren auf ArrowRight/PageDown)
    for key in ["ArrowRight", "PageDown"]:
        try:
            page.keyboard.press(key)
            page.wait_for_timeout(1200)
            return True
        except Exception:
            pass
    # 2) typische Next-Selectoren durchprobieren
    selectors = [
        ".slick-next", ".swiper-button-next", ".carousel-control-next",
        "[aria-label*='weiter' i]", "[aria-label*='next' i]",
        "button:has-text('Weiter')", "button:has-text('Nächste')",
        ".next", ".arrow-right"
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click()
                page.wait_for_timeout(1200)
                return True
        except Exception:
            continue
    return False

# ---------- JSON helper (NaN -> None) ----------
def df_records(df: pd.DataFrame):
    return df.where(pd.notna(df), None).to_dict(orient="records")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="de-DE", timezone_id="Europe/Berlin",
            viewport={"width": 2400, "height": 1400},  # breit: zweiter Tag hat Platz
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        )
        page = context.new_page()
        page.goto(URL, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(2500)  # Grundpuffer

        # ---- Slide 1 (heute)
        html1 = _wait_ready(page, min_tables=4, min_headers=1, timeout_s=60)
        Path(RAW1_HTML).write_text(html1, encoding="utf-8")
        t1, h1 = _counts_from_html(html1)

        # ---- Slide 2 (morgen) erzwingen
        had_next = _try_next_slide(page)
        page.wait_for_timeout(1200)
        html2 = page.content()
        # wenn HTML wirklich anders ist: erneut auf readiness warten
        if hashlib.md5(html1.encode("utf-8")).hexdigest() != hashlib.md5(html2.encode("utf-8")).hexdigest():
            html2 = _wait_ready(page, min_tables=4, min_headers=1, timeout_s=30)
            Path(RAW2_HTML).write_text(html2, encoding="utf-8")
            t2, h2 = _counts_from_html(html2)
        else:
            html2, t2, h2 = "", 0, 0

        context.close()
        browser.close()

    # ---- Tabellen extrahieren & zusammenführen
    frames_all = extract_tables(html1)
    if html2:
        frames_all += extract_tables(html2)

    # Diagnose
    meta = {
        "url": URL,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "slide1": {"tables": t1, "headers": h1},
        "slide2": {"tried_next": had_next, "tables": t2, "headers": h2, "captured": bool(html2)},
        "frames_total": len(frames_all),
        "locale": "de-DE",
        "timezone": "Europe/Berlin",
    }

    # CSV + JSON schreiben
    if frames_all:
        df_all = pd.concat(frames_all, ignore_index=True, join="outer")
        df_all.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

        json_obj = {
            "meta": meta,
            "tables": {str(i): df_records(frames_all[i]) for i in range(len(frames_all))},
            "combined": df_records(df_all),
        }
    else:
        # Fallback: gar keine Tabellen
        soup = BeautifulSoup(html1 or "", "lxml")
        items = [el.get_text(" ", strip=True) for el in soup.select("div, li, p") if el.get_text(strip=True)]
        json_obj = {"meta": {**meta, "note": "no tables found, raw text extracted"},
                    "text_blocks": items[:500]}

    # Striktes JSON (kein NaN)
    Path(OUT_JSON).write_text(json.dumps(json_obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    print("Fertig. Meta:", meta)

if __name__ == "__main__":
    main()
