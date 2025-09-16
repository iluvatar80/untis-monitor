# untis_normalize.py
# Normalisierung + Dubletten-Entfernung, jetzt mit Erhalt von Durchstreichungen (HTML)
# Liest webuntis_subst_raw_1.html (heute) und webuntis_subst_raw_2.html (morgen)
# und schreibt untis_subst_normalized.json / .csv

from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
from datetime import date, timedelta
import json

# Neu: HTML-Sanitizer für Strikethrough erhalten
from tools.html_keep_strike import extract_cell_html, extract_cell_text

RAW1 = Path("webuntis_subst_raw_1.html")  # heute
RAW2 = Path("webuntis_subst_raw_2.html")  # morgen (optional)

OUT_JSON = Path("untis_subst_normalized.json")
OUT_CSV  = Path("untis_subst_normalized.csv")

# ---------- HTML -> DataFrames ----------

def _uniq_headers(headers):
    out, seen = [], {}
    for i, h in enumerate(headers):
        name = (h or "").strip() or f"col_{i+1}"
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name}_{seen[name]}"
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
        # Fallback: erste Zeile als Header verwenden, wenn sie wie ein Header aussieht
        if not headers and rows:
            cells0 = rows[0].find_all(["th", "td"])  # TD erlauben
            if cells0:
                cand = [c.get_text(strip=True) for c in cells0]
                tokens = [t.lower() for t in cand]
                expected = {"stunde", "klassen", "klasse", "fach", "lehrkraft", "vertretungstext"}
                if len(expected.intersection(tokens)) >= 2:
                    headers = cand
                    start_idx = 1
        data_rows_text = []
        data_rows_html = []
        for r in rows[start_idx:]:
            cells = r.find_all(["td", "th"])
            if not cells:
                continue
            row_text = [c.get_text(separator=" ", strip=True) for c in cells]
            row_html = [extract_cell_html(c) for c in cells]
            if any(cell for cell in row_text):
                data_rows_text.append(row_text)
                data_rows_html.append(row_html)
        if not data_rows_text:
            continue
        maxlen = max(len(r) for r in data_rows_text)
        if headers:
            if len(headers) < maxlen:
                headers = headers + [f"col_{i+1}" for i in range(len(headers), maxlen)]
            elif len(headers) > maxlen:
                headers = headers[:maxlen]
        else:
            headers = [f"col_{i+1}" for i in range(maxlen)]
        headers = _uniq_headers(headers)
        normalized_text = [r + [""] * (maxlen - len(r)) for r in data_rows_text]
        normalized_html = [r + [""] * (maxlen - len(r)) for r in data_rows_html]
        df_text = pd.DataFrame(normalized_text, columns=headers)
        df_html = pd.DataFrame(normalized_html, columns=[h + "__html" for h in headers])
        df = pd.concat([df_text, df_html], axis=1)
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


# ---------- Normalisierung / Mapping ----------

def _nz_series(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str)


def _pick_best_name(df_all: pd.DataFrame, *candidates: str):
    """Wie _pick_best, aber gibt den Spaltennamen zurück (für HTML-Mapping)."""
    normcols = {c.lower(): c for c in df_all.columns}
    cand_cols = []
    for cand in candidates:
        key = cand.lower()
        if key in normcols:
            cand_cols.append(normcols[key])
        else:
            for col in df_all.columns:
                if col.lower().startswith(key):
                    cand_cols.append(col)
    seen = set()
    cand_cols = [c for c in cand_cols if not (c in seen or seen.add(c))]
    if not cand_cols:
        return None
    scored = []
    for col in cand_cols:
        s = _nz_series(df_all[col])
        non_empty = (s.str.strip() != "").sum()
        scored.append((non_empty, col))
    scored.sort(reverse=True)
    return scored[0][1]


def _series_text(df: pd.DataFrame, col_name: str | None) -> pd.Series:
    if not col_name or col_name not in df.columns:
        return pd.Series([""] * len(df))
    return _nz_series(df[col_name])


def _series_html(df: pd.DataFrame, col_name: str | None) -> pd.Series:
    if not col_name:
        return pd.Series([""] * len(df))
    html_col = f"{col_name}__html"
    if html_col in df.columns:
        return _nz_series(df[html_col])
    # Fallback: Text
    return _series_text(df, col_name)


def _clean_ws(val: str) -> str:
    s = str(val)
    return " ".join(s.split())


def main():
    today = date.today()
    datum1 = today.strftime("%d.%m.%Y")
    datum2 = (today + timedelta(days=1)).strftime("%d.%m.%Y")

    frames = []
    frames += load_frames_for_day(RAW1, datum1)
    frames += load_frames_for_day(RAW2, datum2)

    if not frames:
        alt1 = Path("raw_1.html")
        alt2 = Path("raw_2.html")
        frames += load_frames_for_day(alt1, datum1)
        frames += load_frames_for_day(alt2, datum2)
    if not frames:
        raise SystemExit("Keine raw_HTML-Dateien gefunden (webuntis_subst_raw_1.html / _2.html).")

    df_all = pd.concat(frames, ignore_index=True, sort=False)

    # Spaltenwahl (Textebene), ermittelt die besten Spaltennamen
    klasse_col = _pick_best_name(df_all, "Klassen", "Klasse", "Klasse(n)", "klassen", "klasse", "klasse(n)", "col_4")
    stunde_col = _pick_best_name(df_all, "Stunde", "stunde", "std", "col_3")
    fach_col   = _pick_best_name(df_all, "Fach", "fach", "col_5")
    lehr_col   = _pick_best_name(df_all, "Lehrkraft", "lehrkraft", "lehrer", "vertretung", "col_6")
    text_col   = _pick_best_name(df_all, "Vertretungstext", "vertretungstext", "bemerkung", "bemerkungen", "col_7")

    # Serien holen (Text & HTML)
    klasse   = _series_text(df_all, klasse_col)
    stunde   = _series_text(df_all, stunde_col)
    fach_txt = _series_text(df_all, fach_col)
    leh_txt  = _series_text(df_all, lehr_col)
    txt_txt  = _series_text(df_all, text_col)

    fach_html = _series_html(df_all, fach_col)
    leh_html  = _series_html(df_all, lehr_col)
    txt_html  = _series_html(df_all, text_col)

    datum    = df_all.get("__datum", pd.Series([datum1] * len(df_all)))

    # Header-Zeilen erkennen (falls "Stunde"/"Klassen" als Zellen auftauchen)
    is_header = (
        _nz_series(stunde).str.strip().str.lower().eq("stunde") &
        _nz_series(klasse).str.strip().str.lower().isin(["klassen", "klasse", "klasse(n)"])
    )

    # Info-Zeilen: irgendeine Zelle beginnt mit "Klassen:"
    def _row_is_info(row) -> bool:
        for v in row.values.tolist():
            if isinstance(v, str) and v.strip().startswith("Klassen:"):
                return True
        return False

    is_info = df_all.apply(_row_is_info, axis=1)

    # Datenzeilen: nicht Header, nicht Info, und mind. ein Nutzfeld gefüllt
    has_any = (
        _nz_series(klasse).str.strip().ne("") |
        _nz_series(stunde).str.strip().ne("") |
        _nz_series(fach_txt).str.strip().ne("") |
        _nz_series(leh_txt).str.strip().ne("") |
        _nz_series(txt_txt).str.strip().ne("")
    )
    mask_data = (~is_header) & (~is_info) & has_any

    df_data = pd.DataFrame({
        "gruppe": 2,
        "datum": _nz_series(datum),
        "quelle_table_index": df_all.get("table_index", pd.Series([None] * len(df_all))),
        "klasse": _nz_series(klasse),
        "stunde": _nz_series(stunde),
        # WICHTIG: diese Felder enthalten HTML (Strikethrough sichtbar)
        "fach":   _nz_series(fach_html),
        "lehrkraft": _nz_series(leh_html),
        "text":   _nz_series(txt_html),
    })
    df_data = df_data[mask_data].copy()

    # Info-Zeilen (gruppe=1)
    col1 = df_all.get("col_1", pd.Series([""] * len(df_all)))
    info_klasse = _nz_series(klasse)
    fallback = _nz_series(col1)
    info_text = info_klasse.where(info_klasse.str.startswith("Klassen:"), fallback)

    df_info = pd.DataFrame({
        "gruppe": 1,
        "datum": _nz_series(datum),
        "quelle_table_index": df_all.get("table_index", pd.Series([None] * len(df_all))),
        "klasse": _nz_series(info_text),
        "stunde": "",
        "fach": "",
        "lehrkraft": "",
        "text": "",
    })
    df_info = df_info[is_info].copy()

    # Zusammenführen & bereinigen
    df_out = pd.concat([df_data, df_info], ignore_index=True)
    for c in ["klasse", "stunde", "fach", "lehrkraft", "text", "datum"]:
        df_out[c] = df_out[c].map(_clean_ws)

    # Dubletten entfernen – nach TEXTINHALT (HTML vorher in Text umwandeln)
    def _strip_html_series(s: pd.Series) -> pd.Series:
        return s.apply(lambda v: BeautifulSoup(v or "", "lxml").get_text(" ", strip=True))

    df_out["__fach_txt"] = _strip_html_series(df_out["fach"]) \
        if "fach" in df_out.columns else ""
    df_out["__lehr_txt"] = _strip_html_series(df_out["lehrkraft"]) \
        if "lehrkraft" in df_out.columns else ""
    df_out["__txt_txt"] = _strip_html_series(df_out["text"]) \
        if "text" in df_out.columns else ""

    df_out = df_out.drop_duplicates(
        subset=["datum", "klasse", "stunde", "__fach_txt", "__lehr_txt", "__txt_txt"], keep="first"
    ).reset_index(drop=True)

    df_out = df_out.drop(columns=["__fach_txt", "__lehr_txt", "__txt_txt"], errors="ignore")

    # Schreiben
    OUT_JSON.write_text(
        json.dumps(df_out.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    df_out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"OK. {len(df_out)} Zeilen → {OUT_CSV.name} / {OUT_JSON.name}")

if __name__ == "__main__":
    main()
