# untis_report.py
# Erzeugt einen HTML-Report mit Suche/Sortierung aus einer Clean-CSV.
# Robust: prüft Eingabe, meldet Fehler, gibt absoluten Ausgabe-Pfad aus.

import argparse, html, sys, traceback
from pathlib import Path
from datetime import datetime
import pandas as pd
import webbrowser

DEF_IN  = "untis_subst_8c_clean.csv"
DEF_OUT = "report_8c.html"

TPL = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<link rel="preconnect" href="https://cdn.jsdelivr.net"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/datatables.net-dt@1.13.8/css/jquery.dataTables.min.css"/>
<style>
  body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,"Helvetica Neue",Arial,sans-serif;margin:16px;}}
  header{{margin-bottom:12px}}
  .meta{{color:#555;font-size:0.9rem}}
  table.dataTable thead th{{white-space:nowrap}}
  @media (max-width:700px){{ table{{font-size:0.95rem}} }}
</style>
{meta_refresh}
</head>
<body>
<header>
  <h1 style="margin:0 0 4px 0">{h1}</h1>
  <div class="meta">Datum: <strong>{datum}</strong>
    &nbsp;•&nbsp; Klasse(n): <strong>{klassen}</strong>
    &nbsp;•&nbsp; Stand: {now}
  </div>
</header>

<table id="tbl" class="display" style="width:100%">
  <thead>
    <tr>
{thead}
    </tr>
  </thead>
  <tbody>
{tbody}
  </tbody>
</table>

<script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/datatables.net@1.13.8/js/jquery.dataTables.min.js"></script>
<script>
  $(function(){{
    $('#tbl').DataTable({{
      pageLength: 50,
      order: [[2, 'asc']],   // 3. Spalte = Stunde
      columnDefs: [ {{ targets: 2, type: 'num' }} ]
    }});
  }});
</script>
</body>
</html>
"""

def run(input_csv: Path, output_html: Path, title: str|None, refresh: int, do_open: bool):
    if not input_csv.exists():
        raise FileNotFoundError(f"Eingabedatei nicht gefunden: {input_csv}")

    df = pd.read_csv(input_csv, dtype=str, encoding="utf-8-sig").fillna("")
    expected = ["Datum","Klassen","Stunde","Fach","Lehrkraft","Vertretungstext"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Fehlende Spalten in {input_csv.name}: {missing}")

    datum_set   = sorted({x for x in df["Datum"].astype(str) if x.strip()})
    klasse_set  = sorted({x.strip() for x in df["Klassen"].astype(str) if x.strip()})
    datum_info  = ", ".join(datum_set) if datum_set else "—"
    klassen_info= ", ".join(klasse_set) if klasse_set else "—"
    now_str     = datetime.now().strftime("%d.%m.%Y %H:%M")

    page_title = title or (f"Vertretungen {('/'.join(klasse_set) or '')}".strip() or "Vertretungen")

    thead = "".join(f"      <th>{html.escape(c)}</th>\n" for c in expected)
    tbody = ""
    for _, row in df.iterrows():
        cells = [row.get(c,"") for c in expected]
        tds = "".join(f"<td>{html.escape(str(v))}</td>" for v in cells)
        tbody += f"    <tr>{tds}</tr>\n"

    meta_refresh = f'<meta http-equiv="refresh" content="{refresh}"/>' if refresh > 0 else ""

    html_out = TPL.format(
        title=html.escape(page_title),
        h1=html.escape(page_title),
        datum=html.escape(datum_info),
        klassen=html.escape(klassen_info),
        now=html.escape(now_str),
        thead=thead,
        tbody=tbody,
        meta_refresh=meta_refresh
    )

    output_html.write_text(html_out, encoding="utf-8")
    print(f"OK: {output_html.resolve()}")
    if do_open:
        webbrowser.open(output_html.resolve().as_uri())

def main():
    ap = argparse.ArgumentParser(description="Erzeuge HTML-Report aus Clean-CSV.")
    ap.add_argument("-i","--input", default=DEF_IN, help="CSV-Eingabe (default: %(default)s)")
    ap.add_argument("-o","--output", default=DEF_OUT, help="HTML-Ausgabe (default: %(default)s)")
    ap.add_argument("-t","--title", default=None, help="Seitentitel/Überschrift")
    ap.add_argument("-r","--refresh", type=int, default=0, help="Auto-Refresh in Sekunden (0=aus)")
    ap.add_argument("--open", action="store_true", help="Nach dem Erzeugen im Browser öffnen")
    args = ap.parse_args()

    try:
        run(Path(args.input), Path(args.output), args.title, args.refresh, args.open)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
