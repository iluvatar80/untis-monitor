# untis_normalize.py
# Normalisiert die aus dem WebUntis-Monitor extrahierten Tabellen zu
# Klasse / Stunde / Fach / Lehrkraft / Text (+ Datum, soweit erkennbar).

import json, re
from bs4 import BeautifulSoup
import pandas as pd

JSON_PATH = "webuntis_subst.json"
RAW_HTML = "webuntis_subst_raw.html"
OUT_CSV = "untis_subst_normalized.csv"
OUT_JSON = "untis_subst_normalized.json"

def load_tables():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    tables = data.get("tables", {})
    tab_list = []
    for k, rows in tables.items():
        ti = rows[0].get("table_index") if rows else None
        if ti is not None:
            tab_list.append({"key": k, "rows": rows, "ti": ti})
    tab_list.sort(key=lambda x: x["ti"])
    return tab_list

HDR_KEYS = {"Stunde","Klassen","Fach","Lehrkraft","Vertretungstext"}

def cols_of(rows):
    c=set()
    for r in rows:
        c.update(r.keys())
    return list(c)

def group_tables(tab_list):
    """Gruppiert: Header-Tabelle (mit Spaltennamen) + die danach folgenden Datentabellen."""
    groups = []
    current = None
    for t in tab_list:
        c = cols_of(t["rows"])
        is_header = (len(t["rows"]) <= 2) and any(
            any(hk.lower() in col.lower() for col in c) for hk in HDR_KEYS
        )
        if is_header:
            current = {"header_ti": t["ti"], "tables": [], "date": None}
            groups.append(current)
        else:
            if current is None:  # falls Seite ohne erkannten Header beginnt
                current = {"header_ti": None, "tables": [], "date": None}
                groups.append(current)
            current["tables"].append(t)
    return groups

def find_date_for_header_ti(html_text, header_ti):
    soup = BeautifulSoup(html_text, "lxml")
    all_tables = soup.find_all("table")
    if header_ti is None or header_ti >= len(all_tables):
        return None
    node = all_tables[header_ti]

    # Texte in den vorangehenden Geschwistern einsammeln (kleines Fenster)
    txts = []
    sib = node.previous_sibling
    for _ in range(8):
        if sib is None:
            break
        try:
            s = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
        except Exception:
            s = ""
        if s:
            txts.append(s)
        sib = sib.previous_sibling
    blob = " | ".join(reversed(txts))

    # Datumsmuster: z.B. "Di 17.09.2025" oder "17.09.2025" oder "17.09."
    m = re.search(r'((?:Mo|Di|Mi|Do|Fr|Sa|So)\w*\s*)?(\d{1,2}\.\d{1,2}\.\d{2,4})', blob)
    if m:
        return m.group(0)
    m2 = re.search(r'(\d{1,2}\.\d{1,2}\.)', blob)
    if m2:
        return m2.group(1)
    return None

def first_nonempty(d, keys):
    for k in keys:
        v = d.get(k, "")
        if isinstance(v, str):
            v = v.strip()
        if v:
            return v
    return ""

def normalize(groups, html_text):
    # Datum je Gruppe bestimmen
    for g in groups:
        g["date"] = find_date_for_header_ti(html_text, g["header_ti"])

    out_rows = []
    for gid, g in enumerate(groups, start=1):
        for t in g["tables"]:
            for r in t["rows"]:
                klasse = first_nonempty(r, ["Klassen","Klasse","col_1"])
                stunde = first_nonempty(r, ["Stunde","col_3"])
                fach   = first_nonempty(r, ["Fach","col_5"])
                lehr   = first_nonempty(r, ["Lehrkraft","Lehrer","col_6"])
                text   = first_nonempty(r, ["Vertretungstext","Text","Info","Bemerkung","col_7"])

                # Leere/Trennzeilen überspringen
                if not any([klasse, stunde, fach, lehr, text]):
                    continue

                out_rows.append({
                    "gruppe": gid,
                    "datum": g.get("date") or "",
                    "quelle_table_index": t["ti"],
                    "klasse": klasse,
                    "stunde": stunde,
                    "fach": fach,
                    "lehrkraft": lehr,
                    "text": text
                })

    df = pd.DataFrame(out_rows)
    if df.empty:
        return df

    # Stunde numerisch sortierbar machen
    df["stunde_num"] = pd.to_numeric(df["stunde"], errors="coerce")
    df.sort_values(
        ["datum","klasse","stunde_num","fach","lehrkraft","text","quelle_table_index"],
        inplace=True, na_position="last"
    )
    df.drop(columns=["stunde_num"], inplace=True)

    # Dubletten entfernen
    df = df.drop_duplicates(subset=["datum","klasse","stunde","fach","lehrkraft","text"])
    return df

def main():
    tabs = load_tables()
    groups = group_tables(tabs)
    with open(RAW_HTML, "r", encoding="utf-8") as f:
        html_text = f.read()

    df = normalize(groups, html_text)

    if df.empty:
        print("Keine verwertbaren Datenzeilen erkannt.")
        return

    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    df.to_json(OUT_JSON, orient="records", force_ascii=False, indent=2)
    print(f"OK. {len(df)} Zeilen → {OUT_CSV} / {OUT_JSON}")

if __name__ == "__main__":
    main()
