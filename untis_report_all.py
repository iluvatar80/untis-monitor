# untis_report_all.py
# Report mit Datum-/Klassen-Dropdowns, Permalinks (&refresh) und Tabellenlinien.
# Robuster Datums-Fallback pro Gruppe (zeigt heute + morgen zuverlässig).

import html, json, re
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

    // Hilfsfunktionen
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

    // URL-Parameter (vor Init)
    var params     = new URLSearchParams(window.location.search);
    var clsParam   = params.get('cls')   || params.get('class') || params.get('c');
    var dateParam  = params.get('date')  || params.get('d');
    var refreshSec = parseInt(params.get('refresh') || params.get('r') || '0', 10);

    // Custom-Filter registrieren
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

    // DataTable initialisieren
    var table = $('#tbl').DataTable({{
      pageLength: 50,
      order: [[0,'asc'],[1,'asc'],[2,'asc']],
      columnDefs: [{{ targets: 2, type: 'num' }}]
    }});

    // Events binden
    $('#dateSel, #classSel').on('change', function(){{ table.draw(); }});

    // Voreinstellungen anwenden + initial zeichnen
    if (dateParam) selectInsensitive('dateSel',  dateParam);
    if (clsParam)  selectInsensitive('classSel', clsParam);
    table.draw();  // wichtig: Permalink filtert sofort

    // Auto-Refresh (optional)
    if (refreshSec > 0) {{
      setTimeout(function() {{
        const url = new URL(window.location.href);
        url.searchParams.set('v', Date.now().toString()); // Cache-Bust
        location.href = url.toString();
      }}, Math.max(5, refreshSec) * 1000);
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

    # Robuste Datumszuweisung pro Gruppe
    def _parse_date_any(s: str):
        s = (s or "").strip()
        if not s:
            return None
        m = re.search(r'(?:Mo|Di|Mi|Do|Fr|Sa|So)?\\s*(\\d{1,2}\\.\\d{1,2}\\.(\\d{2,4})?)', s)
        if not m:
            return None
        d = m.group(1)
        parts = d.strip(".").split(".")
        if len(parts) == 2:
            y = datetime.now().year
            d = f"{parts[0]}.{parts[1]}.{y}"
        elif len(parts) == 3 and len(parts[2]) == 2:
            d = f"{parts[0]}.{parts[1]}.20{parts[2]}"
        try:
            return datetime.strptime(d, "%d.%m.%Y").date()
        except Exception:
            return None

    groups = [g for g in df["gruppe"].dropna().unique()]
    if "quelle_table_index" in df.columns:
        groups.sort(key=lambda g: df.loc[df["gruppe"] == g, "quelle_table_index"].min())
    else:
        groups.sort()

    known = {}
    for g in groups:
        vals = df.loc[df["gruppe"] == g, "datum"].dropna().unique()
        parsed = [_parse_date_any(v) for v in vals]
        parsed = [p for p in parsed if p]
        if parsed:
            known[g] = min(parsed)

    if known:
        first_known_group = min(known.keys(), key=lambda gr: groups.index(gr))
        base_idx = groups.index(first_known_group)
        base_date = known[first_known_group]
    else:
        base_idx = 0
        base_date = datetime.now().date()

    mapping = {}
    for i, g in enumerate(groups):
        mapping[g] = known.get(g, base_date + timedelta(days=(i - base_idx)))

    df["Datum"] = df["gruppe"].map(mapping).apply(lambda d: d.strftime("%d.%m.%Y"))

    # Zielspalten vereinheitlichen + sortieren
    df["Klassen"] = df["klasse"].fillna("")
    df["Stunde"] = df["stunde"].fillna("")
    df["Fach"] = df["fach"].fillna("")
    df["Lehrkraft"] = df["lehrkraft"].fillna("")
    df["Vertretungstext"] = df["text"].fillna("")

    df["Stunde_num_"] = pd.to_numeric(df["Stunde"], errors="coerce")
    df.sort_values(["Datum", "Klassen", "Stunde_num_", "Fach", "Lehrkraft"], inplace=True, na_position="last")
    df = df[["Datum", "Klassen", "Stunde", "Fach", "Lehrkraft", "Vertretungstext"]]

    # Dropdown-Optionen erzeugen
    def parse_date(s):
        try:
            return datetime.strptime(s, "%d.%m.%Y")
        except Exception:
            return datetime.max

    dates = [d for d in sorted(df["Datum"].unique(), key=parse_date) if d]
    classes = sorted({c.strip() for c in df["Klassen"].astype(str) if c.strip()})

    date_options = "\n".join(f'          <option value="{html.escape(d)}">{html.escape(d)}</option>' for d in dates)
    class_options = "\n".join(f'          <option value="{html.escape(c)}">{html.escape(c)}</option>' for c in classes)

    # Tabellenkörper
    rows = []
    for _, r in df.iterrows():
        cells = [r[c] for c in ["Datum", "Klassen", "Stunde", "Fach", "Lehrkraft", "Vertretungstext"]]
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
