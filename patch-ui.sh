#!/usr/bin/env bash
set -euo pipefail
cd /opt/seller-control

PYFILE="backend/app/main.py"
cp -a "$PYFILE" "${PYFILE}.bak.$(date +%s)"

python3 - <<'PY'
from pathlib import Path
p = Path("backend/app/main.py")
s = p.read_text(encoding="utf-8")

# nur anhängen, wenn /ui noch nicht existiert
if '@app.get("/ui"' in s:
    print("ℹ️  /ui existiert bereits – kein Patch nötig.")
else:
    html = r'''
@app.get("/ui", response_class=HTMLResponse)
def ui_page():
    return """<!doctype html>
<html lang='de'>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width, initial-scale=1'/>
  <title>Seller-Control Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
  <style>
    .card { @apply bg-white shadow rounded-2xl p-4; }
    .btn  { @apply px-4 py-2 rounded-lg bg-black text-white hover:bg-gray-800; }
    .btn2 { @apply px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200; }
    .stat { @apply text-3xl font-semibold; }
    .statlabel { @apply text-sm text-gray-500; }
    .grid4 { @apply grid gap-4 grid-cols-2 md:grid-cols-4; }
  </style>
</head>
<body class="bg-gray-50 min-h-screen">
<div class="max-w-6xl mx-auto px-4 py-6">
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-2xl font-bold">Seller-Control Dashboard</h1>
    <a href="/" class="text-sm text-blue-600 hover:underline">klassische Ansicht</a>
  </div>

  <!-- Controls -->
  <div class="grid md:grid-cols-2 gap-4">
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Aktionen</h2>
      </div>
      <div class="space-y-3">
        <div>
          <label class="block text-sm text-gray-600 mb-1">Account ID</label>
          <input id="accId" type="number" class="w-full border rounded-lg px-3 py-2" placeholder="z.B. 1" value="1">
        </div>
        <div class="flex gap-2 flex-wrap">
          <button class="btn" onclick="syncOrders()">Sync Orders (7 Tage)</button>
          <button class="btn2" onclick="pullReports()">Pull Reports</button>
          <button class="btn2" onclick="runRecon()">Run Recon</button>
        </div>
        <div id="msg" class="text-sm text-gray-700"></div>
      </div>
    </div>

    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-semibold">Report-Übersicht</h2>
      </div>
      <div class="grid4">
        <div><div id="c_returns" class="stat">–</div><div class="statlabel">Returns</div></div>
        <div><div id="c_removals" class="stat">–</div><div class="statlabel">Removals</div></div>
        <div><div id="c_adjustments" class="stat">–</div><div class="statlabel">Ledger Events</div></div>
        <div><div id="c_reims" class="stat">–</div><div class="statlabel">Reimbursements</div></div>
      </div>
    </div>
  </div>

  <!-- Output -->
  <div class="card mt-4">
    <h2 class="text-lg font-semibold mb-2">Ausgabe</h2>
    <div id="out" class="prose max-w-none whitespace-pre-wrap text-sm"></div>
  </div>
</div>

<script>
function q(id){ return document.getElementById(id); }
function setMsg(t){ q('msg').textContent = t; }
function setOut(html){ q('out').innerHTML = html; }
function setCounts(c){
  if(!c) return;
  q('c_returns').textContent = c.returns ?? '–';
  q('c_removals').textContent = c.removals ?? '–';
  q('c_adjustments').textContent = c.adjustments ?? '–';
  q('c_reims').textContent = c.reimbursements ?? '–';
}

function parseCountsFromHtml(html){
  const m = html.match(/returns=(\d+).*?removals=(\d+).*?adjustments=(\d+).*?reimbursements=(\d+)/i);
  if(!m) return null;
  return {returns:+m[1], removals:+m[2], adjustments:+m[3], reimbursements:+m[4]};
}

async function syncOrders(){
  const id = q('accId').value || 1;
  setMsg('Orders werden synchronisiert …');
  try{
    const r = await fetch(`/api/orders/sync?account_id=${id}&days=7`, {method:'POST'});
    const j = await r.json();
    setMsg(`✅ Orders: ${JSON.stringify(j)}`);
  }catch(e){
    setMsg('❌ ' + e);
  }
}

async function pullReports(){
  const id = q('accId').value || 1;
  setMsg('Reports werden gezogen …');
  try{
    const r = await fetch(`/api/reports/pull?account_id=${id}`, {method:'POST'});
    const t = await r.text(); // Endpoint liefert HTML
    setOut(t);
    setMsg('✅ Reports aktualisiert');
    setCounts(parseCountsFromHtml(t));
  }catch(e){
    setMsg('❌ ' + e);
  }
}

async function runRecon(){
  const id = q('accId').value || 1;
  setMsg('Recon wird ausgeführt …');
  try{
    const r = await fetch(`/api/recon/run?account_id=${id}`, {method:'POST'});
    const t = await r.text();
    setOut(t);
    setMsg('✅ Recon fertig');
  }catch(e){
    setMsg('❌ ' + e);
  }
}
</script>
</body></html>"""
'''
    s += "\n" + html + "\n"
    p.write_text(s, encoding="utf-8")
    print("✅ /ui an main.py angehängt.")
PY

# Commit, Push, Deploy mit Logs
git add backend/app/main.py
git commit -m "feat(ui): add new /ui dashboard with stat cards + actions"
git push origin main

/opt/seller-control/update.sh -l
