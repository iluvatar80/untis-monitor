# untis_normalize.py
# Liest webuntis_subst_raw_1.html (heute) und webuntis_subst_raw_2.html (morgen),
# extrahiert Tabellen, mappt auf ein einheitliches Schema und schreibt
# untis_subst_normalized.json / .csv

from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
from datetime import date, timedelta
import json
import re

RAW1 = Path("webuntis_subst_raw_1.html")  # heute
RAW2 = Path("webuntis_subst_raw_2.html")  # morgen (optional)

OUT_JSON = Path("untis_subst_normalized.json")
OUT_CSV  = Path("untis_subst_normalized.csv")

# ---------- HTML -> DataFrames (wie im Scraper) ----------
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

def extract_tables_from_html(html: str):
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
                headers = [th.get_text(strip=True) for h in ths]
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

def load_frames_for_day(path: Path, datum_str: str):
    if not path.exists():
        return []
    html = path.read_text(encoding="utf-8", errors="ignore")
    frames = extract_tables_from_html(html)
    for df in frames:
        df["__datum"] = datum_str
    return frames

def main():
    today = date.today()
    datum1 = today.strftime("%d.%m.%Y")
    datum2 = (today + timedelta(days=1)).strftime("%d.%m.%Y")

    frames = []
    # heute
    frames += load_frames_for_day(RAW1, datum1)
    # morgen (falls vorhanden)
    frames += load_frames_for_day(RAW2, datum2)

    if not frames:
        raise SystemExit("Keine raw_HTML-Dateien gefunden (webuntis_subst_raw_1.html / _2.html).")

    # Alles zusammenführen (später filtern)
    df_all = pd.concat(frames, ignore_index=True, sort=False)

    # Spalten-Mapping mit Fallbacks
    def pick(*cols):
        for c in cols:
            if c in df_all.columns:
                return df_all[c]
        # Fallback leere Spalte
        return pd.Series([""] * len(df_all))

    klasse   = pick("Klassen", "klassen", "col_4")
    stunde   = pick("Stunde", "stunde", "col_3")
    fach     = pick("Fach", "fach", "col_5")
    lehrer   = pick("Lehrkraft", "lehrkraft", "col_6")
    text     = pick("Vertretungstext", "vertretungstext", "col_7")
    datum    = df_all["__datum"] if "__datum" in df_all.columns else pd.Series([""] * len(df_all))

    # Header-Zeilen erkennen und entfernen (z. B. "Stunde/Klassen/Fach/...")
    is_header = (
        stunde.astype(str).str.strip().str.lower().eq("stunde") &
        klasse.astype(str).str.strip().str.lower().eq("klassen")
    )

    # Info-Zeilen "Klassen: 5a, 5b, ..." (ohne reguläre Spalten) als gruppe=1 durchlassen
    col1 = pick("col_1")
    is_info = col1.astype(str).str.strip().str.startswith("Klassen:")

    # Relevante Datenzeilen: nicht Header, und etwas Inhalt vorhanden
    has_any = (
        klasse.astype(str).str.strip().ne("") |
        stunde.astype(str).str.strip().ne("") |
        fach.astype(str).str.strip().ne("") |
        lehrer.astype(str).str.strip().ne("") |
        text.astype(str).str.strip().ne("")
    )

    mask_data = (~is_header) & has_any

    # Normierte Datensätze (gruppe=2)
    df_data = pd.DataFrame({
        "gruppe": 2,
        "datum": datum.fillna(""),
        "quelle_table_index": df_all.get("table_index", pd.Series([None] * len(df_all))),
        "klasse": klasse.fillna(""),
        "stunde": stunde.fillna(""),
        "fach":   fach.fillna(""),
        "lehrkraft": lehrer.fillna(""),
        "text":   text.fillna(""),
    })
    df_data = df_data[mask_data].copy()

    # Info-Datensätze (gruppe=1)
    df_info = pd.DataFrame({
        "gruppe": 1,
        "datum": datum.fillna(""),
        "quelle_table_index": df_all.get("table_index", pd.Series([None] * len(df_all))),
        "klasse": col1.fillna(""),
        "stunde": "",
        "fach": "",
        "lehrkraft": "",
        "text": "",
    })
    df_info = df_info[is_info].copy()

    # Zusammenführen, leere Zeilen entfernen, bereinigen
    df_out = pd.concat([df_data, df_info], ignore_index=True)
    # Whitespace normalisieren
    for c in ["klasse", "stunde", "fach", "lehrkraft", "text", "datum"]:
        df_out[c] = df_out[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()

    # Als JSON (ohne NaN) und CSV schreiben
    OUT_JSON.write_text(
        json.dumps(df_out.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    df_out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"OK. {len(df_out)} Zeilen → {OUT_CSV.name} / {OUT_JSON.name}")

if __name__ == "__main__":
    main()
