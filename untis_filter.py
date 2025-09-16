# untis_filter.py
# CLI-Filter für normalisierte WebUntis-Vertretungen.
# Ausgabe (clean): Datum, Klassen, Stunde, Fach, Lehrkraft, Vertretungstext
#
# Beispiele:
#   python untis_filter.py -c 8c
#   python untis_filter.py -c 5a 5b 5c -d 17.09.2025

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

IN_JSON = "untis_subst_normalized.json"
RAW_HTML = "webuntis_subst_raw.html"


def detect_date_from_html() -> str | None:
    """Versucht ein Datum aus dem zuletzt gescrapten HTML zu lesen."""
    p = Path(RAW_HTML)
    if not p.exists():
        return None
    html = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", html)  # 17.09.2025
    if m:
        return m.group(1)
    m2 = re.search(r"(\d{1,2}\.\d{1,2}\.)", html)  # 17.09.
    if m2:
        return f"{m2.group(1)}{datetime.now().year}"
    return None


def class_matches(klasse: str, wanted: list[str]) -> bool:
    if not klasse:
        return False
    k = str(klasse).lower()
    tokens = re.split(r"[,\s;/|]+", k)
    tokens = [t for t in tokens if t]
    wl = [w.lower() for w in wanted]
    return any((w in tokens) or (w in k) for w in wl)


def to_int_or_none(x):
    try:
        return int(str(x).strip())
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Filtert Vertretungen nach Klassen/Datum und erzeugt Clean-CSV.")
    ap.add_argument("-c", "--class", dest="classes", nargs="+", required=True,
                    help="Eine oder mehrere Klassen, z. B. 8c oder 5a 5b 5c")
    ap.add_argument("-d", "--date", dest="date", default=None,
                    help='Optionales Datum, z. B. "17.09.2025" (Teiltreffer erlaubt).')
    args = ap.parse_args()

    data = json.loads(Path(IN_JSON).read_text(encoding="utf-8"))
    df = pd.DataFrame(data)
    if df.empty:
        print("Keine Daten in", IN_JSON)
        return

    # Datum aus HTML ableiten, wenn leer
    detected = detect_date_from_html()
    if detected:
        mask_empty = df["datum"].isna() | (df["datum"].astype(str).str.strip() == "")
        df.loc[mask_empty, "datum"] = detected

    # Datum (optional) filtern
    if args.date:
        df = df[df["datum"].fillna("").str.contains(re.escape(args.date), case=False, na=False)]

    # Klassen filtern
    df = df[df["klasse"].apply(lambda x: class_matches(str(x), args.classes))]

    # Offensichtliche Meta-/Kopfzeilen entfernen
    df["stunde_num"] = pd.to_numeric(df["stunde"], errors="coerce")
    df = df[df["stunde_num"].notna()]
    df = df[~df["klasse"].astype(str).str.startswith("Klassen:")]

    if df.empty:
        print("Keine Zeilen nach Filter.")
        return

    # Spalten sauber benennen und sortieren
    rename = {
        "datum": "Datum",
        "klasse": "Klassen",
        "stunde": "Stunde",
        "fach": "Fach",
        "lehrkraft": "Lehrkraft",
        "text": "Vertretungstext",
    }
    keep_order = ["Datum", "Klassen", "Stunde", "Fach", "Lehrkraft", "Vertretungstext"]

    df_clean = df.rename(columns=rename)
    df_clean = df_clean[keep_order].copy()

    df_clean["Stunde_num"] = pd.to_numeric(df_clean["Stunde"], errors="coerce")
    df_clean.sort_values(["Datum", "Klassen", "Stunde_num", "Fach", "Lehrkraft"], inplace=True, na_position="last")
    df_clean.drop(columns=["Stunde_num"], inplace=True)

    base = "untis_subst_" + "_".join(args.classes)
    out_csv = base + "_clean.csv"
    out_json = base + "_clean.json"

    df_clean.to_csv(out_csv, index=False, encoding="utf-8-sig")
    df_clean.to_json(out_json, orient="records", force_ascii=False, indent=2)

    print(f"OK. {len(df_clean)} Zeilen → {out_csv} / {out_json}")
    if detected:
        print(f"Hinweis: Datum automatisch erkannt: {detected}")


if __name__ == "__main__":
    main()
