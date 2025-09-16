# untis_normalize.py
# Robustere Normalisierung + Dubletten-Entfernung.
# Pro Spalte wird die "beste" Quelle (max. Nicht-Leer-Werte) gewählt,
# damit Header-Only-Tabellen (mit Spaltennamen) nicht die Daten-Tabellen überdecken.
# Liest webuntis_subst_raw_1.html (heute) und webuntis_subst_raw_2.html (morgen)
# und schreibt untis_subst_normalized.json / .csv

from pathlib import Path
from bs4 import BeautifulSoup
import pandas as pd
from datetime import date, timedelta
import json

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
        if headers:
            if len(headers) < maxlen:
                headers = headers + [f"col_{i+1}" for i in range(len(headers), maxlen)]
            elif len(headers) > maxlen:
                headers = headers[:maxlen]
        else:
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


# ---------- Normalisierung / Mapping ----------

def _nz_series(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str)


def _pick_best(df_all: pd.DataFrame, *candidates: str) -> pd.Series:
    """Wähle unter Kandidaten die Spalte mit den meisten Nicht-Leer-Werten.
    Header und Body sind getrennte Tabellen; Body hat typ. col_3..col_7.
    """
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
        return pd.Series([""] * len(df_all))
    scored = []
    for col in cand_cols:
        s = _nz_series(df_all[col])
        non_empty = (s.str.strip() != "").sum()
        scored.append((non_empty, col))
    scored.sort(reverse=True)
    best_col = scored[0][1]
    return df_all[best_col]


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

    # Spaltenwahl mit _pick_best (gegen Header-Only-Kollisionen)
    klasse   = _pick_best(df_all, "Klassen", "Klasse", "Klasse(n)", "klassen", "klasse", "klasse(n)", "col_4")
    stunde   = _pick_best(df_all, "Stunde", "stunde", "std", "col_3")
    fach     = _pick_best(df_all, "Fach", "fach", "col_5")
    lehrer   = _pick_best(df_all, "Lehrkraft", "lehrkraft", "lehrer", "vertretung", "col_6")
    text     = _pick_best(df_all, "Vertretungstext", "vertretungstext", "bemerkung", "bemerkungen", "col_7")
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
        _nz_series(fach).str.strip().ne("") |
        _nz_series(lehrer).str.strip().ne("") |
        _nz_series(text).str.strip().ne("")
    )
    mask_data = (~is_header) & (~is_info) & has_any

    df_data = pd.DataFrame({
        "gruppe": 2,
        "datum": _nz_series(datum),
        "quelle_table_index": df_all.get("table_index", pd.Series([None] * len(df_all))),
        "klasse": _nz_series(klasse),
        "stunde": _nz_series(stunde),
        "fach":   _nz_series(fach),
        "lehrkraft": _nz_series(lehrer),
        "text":   _nz_series(text),
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

    # >>> Dubletten entfernen (nach inhaltlicher Gleichheit)
    df_out = df_out.drop_duplicates(
        subset=["datum", "klasse", "stunde", "fach", "lehrkraft", "text"], keep="first"
    ).reset_index(drop=True)

    # Schreiben
    OUT_JSON.write_text(
        json.dumps(df_out.to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    df_out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"OK. {len(df_out)} Zeilen → {OUT_CSV.name} / {OUT_JSON.name}")

if __name__ == "__main__":
    main()
