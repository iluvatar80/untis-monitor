# untis_report_all.py
# Report mit Datum-/Klassen-Dropdowns, Permalinks und Tabellenlinien.
# Permalink-Beispiele: ?cls=8c  |  ?cls=8c&date=16.09.2025  |  …&refresh=120

import html, json
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import webbrowser

IN_JSON = "untis_subst_normalized.json"
OUT_HTML = "report_all.html"

TPL = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>

<link rel="stylesheet" href="https://cdn.datatables.net/1.13.8/css/jquery.dataTables.min.css"/>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>

<style>
  body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,"Helvetica Neue",Arial,sans-serif;margin:16px}}
  header{{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin-bottom:12px}}
  .meta{{color:#555;font-size:.9rem}}
  label{{font-size:.9rem;margin-right:6px}}
  select{{padding:4px 6px;border:1px solid #ccc;border-radius:6px}}
  .filters{{display:flex;gap:10px;align-items:center}}
  table.dataTable{{border-collapse:collapse;width:100%}}
  table.dataTable th, table.dataTable td{{border:1px solid #ddd;padding:6px 8px}}
  table.dataTable thead th{{background:#f6f6f6;white-space:nowrap}}
  @media (max-width:700px){{ table{{font-size:.95rem}} .filters{{flex-direction:column;align-items:flex-start}} }}
</style>
</head>
<body>
  <header>
    <div>
      <h1 style="margin:0 0 4px 0">{title}</h1>
      <div class="meta">Stand: {now}</div>
    </div>
    <div class="filters">
      <div>
        <label for="dateSel">Datum:</label>
        <select id="dateSel">
          <option value="">Alle</option>
{date_options}
        </select>
      </div>
      <div>
        <label for="classSel">Klasse:</label>
        <select id="classSel">
          <option value="">Alle</option>
{class_options}
        </select>
      </div>
    </div>
  </header>

  <table id="tbl" class="display">
    <thead>
      <tr>
        <th>Datum</th><th>Klassen</th><th>Stunde</th><th>Fach</th><th>Lehrkraft</th><th>Vertretungstext</th>
      </tr>
    </thead>
    <tbody>
{tbody}
    </tbody>
  </table>

<script>
(function(){{  // IIFE
  $(function(){{   // DOM ready

    // --- Hilfsfunktionen ---
    function selectInsensitive(selId, wanted) {{
      if (!wanted) return;
      var val = (''+wanted).trim().toLowerCase();
      var sel = document.getElementById(selId);
      if (!sel) return;
      var match = null;
      for (var i=0;i<sel.options.length;i++) {{
        var opt = sel.options[i];
        if (opt.value.toLowerCase() === val || opt.text.toLowerCase() === val) {{
          match = opt.value; break;
        }}
      }}
      if (match !== null) document.getElementById(selId).value = match;
    }}

    // --- URL-Parameter lesen (vor Init) ---
    var params     = new URLSearchParams(window.location.search);
    var clsParam   = params.get('cls')   || params.get('class') || params.get('c');
    var dateParam  = params.get('date')  || params.get('d');
    var refreshSec = parseInt(params.get('refresh') || params.get('r') || '0', 10);

    // --- Custom-Filter registrieren (vor erster Zeichnung) ---
    $.fn.dataTable.ext.search.push(function(settings, data, dataIndex) {{
      var selDate = ($('#dateSel').val() || '').trim();
      var selCls  = ($('#classSel').val() || '').toLowerCase().trim();

      var rowDate = (data[0] || '').trim();
      var rowCls  = (data[1] || '').toLowerCase();

      if (selDate && rowDate !== selDate) return false;

      if (selCls) {{
        var tokens = rowCls.split(/[\\s,;\\/|]+/).filter(Boolean);
        if (tokens.indexOf(selCls) === -1) return false;
      }}
      return true;
    }});

    // --- DataTable initialisieren ---
    var table = $('#tbl').DataTable({{
      pageLength: 50,
      order: [[0,'asc'],[1,'asc'],[2,'asc']],
      columnDefs: [{{ targets: 2, type: 'num' }}]
    }});

    // --- Events binden ---
    $('#dateSel, #classSel').on('change', function(){{ table.draw(); }});

    // --- Voreinstellungen aus URL anwenden und initial zeichnen ---
    if (dateParam) selectInsensitive('dateSel',  dateParam);
    if (clsParam)  selectInsensitive('classSel', clsParam);
    table.draw();  // WICHTIG: damit Permalink sofort filtert

    // --- Auto-Refresh (optional) ---
    if (refreshSec > 0) {{
      setTimeout(function() {{ location.reload(); }}, Math.max(5, refreshSec) * 1000);
    }}
  }});
}})();
</script>
</body>
</html>
"""

def main():
    data = json.loads(Path(IN_JSON).read_text(encoding="utf-8"))
    df = pd.DataFrame(data)
    if df.empty:
        raise SystemExit("Keine Daten in untis_subst_normalized.json")

    # echte Zeilen, Stunde numerisch, Kopfzeilen raus
    df["stunde_num"] = pd.to_numeric(df["stunde"], errors="coerce")
    df = df[df["stunde_num"].notna()]
    df = df[~df["klasse"].astype(str).str.startswith("Klassen:")]

    # Datum: falls leer, Gruppen -> heute/morgen …
    if df["datum"].fillna("").str.strip().eq("").all():
        groups = sorted(df["gruppe"].dropna().unique())
        base = datetime.now().date()
        mapping = {g: (base + timedelta(days=i)).strftime("%d.%m.%Y") for i, g in enumerate(groups)}
        df["Datum"] = df["gruppe"].map(mapping).fillna("")
    else:
        df["Datum"] = df["datum"].fillna("")

    # Zielspalten vereinheitlichen + sortieren
    df["Klassen"] = df["klasse"].fillna("")
    df["Stunde"] = df["stunde"].fillna("")
    df["Fach"] = df["fach"].fillna("")
    df["Lehrkraft"] = df["lehrkraft"].fillna("")
    df["Vertretungstext"] = df["text"].fillna("")

    df["Stunde_num_"] = pd.to_numeric(df["Stunde"], errors="coerce")
    df.sort_values(["Datum","Klassen","Stunde_num_","Fach","Lehrkraft"], inplace=True, na_position="last")
    df = df[["Datum","Klassen","Stunde","Fach","Lehrkraft","Vertretungstext"]]

    # Dropdown-Optionen erzeugen
    def parse_date(s):
        try:
            return datetime.strptime(s, "%d.%m.%Y")
        except Exception:
            return datetime.max
    dates = [d for d in sorted(df["Datum"].unique(), key=parse_date) if d]
    classes = sorted({c.strip() for c in df["Klassen"].astype(str) if c.strip()})

    date_options  = "\n".join(f'          <option value="{html.escape(d)}">{html.escape(d)}</option>' for d in dates)
    class_options = "\n".join(f'          <option value="{html.escape(c)}">{html.escape(c)}</option>' for c in classes)

    # Tabellenkörper
    rows = []
    for _, r in df.iterrows():
        cells = [r[c] for c in ["Datum","Klassen","Stunde","Fach","Lehrkraft","Vertretungstext"]]
        rows.append("    <tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in cells) + "</tr>")
    tbody = "\n".join(rows)

    html_out = TPL.format(
        title="Vertretungen (alle Klassen / Tage)",
        now=datetime.now().strftime("%d.%m.%Y %H:%M"),
        date_options=date_options or '          <!-- keine Datumsangabe gefunden -->',
        class_options=class_options or '          <!-- keine Klassen gefunden -->',
        tbody=tbody
    )

    Path(OUT_HTML).write_text(html_out, encoding="utf-8")
    print(f"OK: {Path(OUT_HTML).resolve()}")
    webbrowser.open(Path(OUT_HTML).resolve().as_uri())

if __name__ == "__main__":
    main()
