# untis_inspect.py
# Zweck: Analysiert webuntis_subst.json, zeigt Spalten/Zeilen je Tabelle
# und bewertet, welche Tabelle wahrscheinlich die Vertretungen enthält.

import json
from collections import Counter

JSON_PATH = "webuntis_subst.json"

KEYWORDS = [
    "klasse", "klasse(n)", "kl.", "stunde", "fach", "lehrer", "raum",
    "art", "text", "info", "vertreter", "datum", "absenz", "entfall"
]

def score_columns(cols):
    cols_l = [c.lower() for c in cols]
    score = 0
    hits = []
    for kw in KEYWORDS:
        for c in cols_l:
            if kw in c:
                score += 1
                hits.append(kw)
                break
    return score, sorted(set(hits))

def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    tables = data.get("tables", {})
    if not tables:
        print("Keine 'tables' im JSON gefunden. Prüfe webuntis_subst_raw.html oder Skript.")
        return

    print(f"Gefundene Tabellen: {len(tables)}\n")

    ranking = []
    for key, rows in tables.items():
        # Spalten ermitteln
        cols = set()
        for r in rows[:50]:
            cols.update(r.keys())
        cols = list(cols)

        sc, hits = score_columns(cols)
        ranking.append((sc, int(key), len(rows), cols, hits))

    # Nach Score und dann nach Zeilenzahl sortieren
    ranking.sort(key=lambda x: (x[0], x[2]), reverse=True)

    for sc, idx, nrows, cols, hits in ranking:
        print("="*70)
        print(f"Tabelle #{idx} | Zeilen: {nrows} | Score: {sc} | Keyword-Treffer: {', '.join(hits) or '-'}")
        print("Spalten:")
        for c in sorted(cols, key=str.lower):
            print(f"  - {c}")

        # kleine Vorschau
        sample = tables[str(idx)][:2]
        if sample:
            print("Vorschau (erste 1–2 Zeilen):")
            for i, r in enumerate(sample, 1):
                # nur Felder mit Inhalt zeigen
                nonempty = {k: v for k, v in r.items() if str(v).strip()}
                print(f"  {i}: {nonempty}")
        print()

    if ranking:
        best = ranking[0]
        print("="*70)
        print(f"→ Vermutlich relevant: Tabelle #{best[1]} (Score {best[0]}, Zeilen {best[2]})")
        print("  Diese Nummer merken – daraus bauen wir gleich eine normierte CSV.")

if __name__ == "__main__":
    main()
