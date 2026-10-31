#!/usr/bin/env python3
"""AI Spend Tracker — free tool that totals what you spend on AI each month.

Python 3 standard library only. No pip dependencies, no accounts, no
external calls. Subscriptions are stored in data.json next to this file.

Run:  python3 app.py            (serves http://localhost:8000)
      PORT=8901 python3 app.py  (pick a different port)

Endpoints:
  GET  /            the app page
  GET  /api/subs    JSON list of subscriptions
  POST /api/subs    add one: {"name","provider","price","cycle","last_used"}
  POST /api/delete  delete one: {"id": <int>}
  GET  /export.csv  CSV download of all subscriptions
"""

import csv
import io
import json
import os
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
LOCK = threading.Lock()

try:
    import config
    AD_SLOT_HTML = config.AD_SLOT_HTML
    STRIPE_PRO_LINK = config.STRIPE_PRO_LINK
except Exception:  # config.py missing or broken: safe defaults
    AD_SLOT_HTML = ""
    STRIPE_PRO_LINK = "https://example.com/replace-with-stripe-link"

PROVIDERS = [
    "ChatGPT", "Claude", "Midjourney", "Perplexity",
    "Gemini", "Copilot", "API keys", "Custom",
]

# ---------------------------------------------------------------- storage

def load_subs():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_subs(subs):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(subs, f, indent=2)
    os.replace(tmp, DATA_FILE)


def next_id(subs):
    return max((s.get("id", 0) for s in subs), default=0) + 1


def monthly_equivalent(sub):
    """Monthly cost of one subscription, whatever its billing cycle."""
    price = float(sub["price"])
    return price if sub["cycle"] == "monthly" else price / 12.0


# ---------------------------------------------------------------- page

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Spend Tracker — How much are you spending on AI?</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         max-width: 760px; margin: 0 auto; padding: 24px 16px 64px;
         color: #1e1f24; background: #f7f7f8; }
  h1 { font-size: 1.9rem; margin-bottom: 4px; }
  .tagline { color: #555; margin-top: 0; }
  .totals { background: #1e1f24; color: #fff; border-radius: 12px;
            padding: 24px; text-align: center; margin: 24px 0; }
  .totals .big { font-size: 3rem; font-weight: 700; line-height: 1.1; }
  .totals .sub { color: #bbb; margin-top: 6px; }
  .card { background: #fff; border: 1px solid #ddd; border-radius: 12px;
          padding: 20px; margin: 16px 0; }
  label { display: block; font-weight: 600; margin: 12px 0 4px; }
  input, select { width: 100%; padding: 9px; font-size: 1rem;
                  border: 1px solid #ccc; border-radius: 8px; }
  .row { display: flex; gap: 12px; }
  .row > div { flex: 1; }
  button { background: #3d9bff; color: #fff; border: 0; border-radius: 8px;
           padding: 10px 18px; font-size: 1rem; cursor: pointer; margin-top: 16px; }
  button:hover { background: #2a7fe0; }
  button.danger { background: #e5534b; padding: 5px 12px; margin: 0;
                  font-size: 0.85rem; }
  button.secondary { background: #555; }
  table { width: 100%; border-collapse: collapse; }
  td, th { padding: 8px 6px; border-bottom: 1px solid #eee; text-align: left; }
  .badge { display: inline-block; font-size: 0.75rem; font-weight: 700;
           padding: 2px 8px; border-radius: 999px; margin-left: 6px;
           vertical-align: middle; }
  .badge.unused { background: #fff3cd; color: #7a5b00; }
  .badge.dup { background: #fde8e8; color: #8b1a1a; }
  .warn { background: #fff3cd; border: 1px solid #f0d98c; border-radius: 8px;
          padding: 12px 16px; margin: 16px 0; display: none; }
  .warn.show { display: block; }
  .share { display: flex; gap: 8px; align-items: center; }
  .share input { flex: 1; background: #f0f0f0; }
  .share button { margin-top: 0; }
  .ad-slot { border: 1px dashed #bbb; border-radius: 8px; text-align: center;
             color: #999; padding: 18px; margin: 16px 0; font-size: 0.9rem; }
  .premium { border: 2px solid #3d9bff; }
  .premium h2 { margin-top: 0; }
  .price { font-size: 1.4rem; font-weight: 700; }
  .muted { color: #777; font-size: 0.9rem; }
  .empty { color: #777; text-align: center; padding: 12px 0; }
</style>
</head>
<body>
<h1>AI Spend Tracker</h1>
<p class="tagline">How much are you spending on AI every month? Add your subscriptions and find out.</p>

<div class="totals">
  <div class="big" id="total-month">$0.00<span style="font-size:1.2rem"> / month</span></div>
  <div class="sub" id="total-year">$0.00 per year &middot; 0 subscriptions</div>
</div>

<div class="warn" id="dup-warn"></div>

<div class="card">
  <h2>Add a subscription</h2>
  <form id="add-form">
    <label for="name">Name</label>
    <input id="name" required maxlength="100" placeholder="e.g. ChatGPT Plus">
    <div class="row">
      <div>
        <label for="provider">Provider</label>
        <select id="provider">
          <option>ChatGPT</option><option>Claude</option><option>Midjourney</option>
          <option>Perplexity</option><option>Gemini</option><option>Copilot</option>
          <option>API keys</option><option>Custom</option>
        </select>
      </div>
      <div>
        <label for="price">Price ($)</label>
        <input id="price" type="number" step="0.01" min="0" required placeholder="20.00">
      </div>
    </div>
    <div class="row">
      <div>
        <label for="cycle">Billing cycle</label>
        <select id="cycle">
          <option value="monthly">Monthly</option>
          <option value="yearly">Yearly</option>
        </select>
      </div>
      <div>
        <label for="last-used">Last used (optional)</label>
        <input id="last-used" type="date">
      </div>
    </div>
    <button type="submit">Add subscription</button>
  </form>
</div>

<div class="card">
  <h2>Your subscriptions</h2>
  <div id="list"></div>
</div>

<div class="card">
  <h2>Share your number</h2>
  <div class="share">
    <input id="share-line" readonly value="I'm spending $0.00/month on AI">
    <button type="button" id="copy-btn">Copy</button>
  </div>
</div>

<div class="ad-slot">
  <!-- PASTE AD NETWORK CODE HERE -->
  __AD_SLOT_HTML__
</div>

<div class="card premium">
  <h2>Spend Tracker Premium — $2/month</h2>
  <p>Unlimited subscriptions, plus CSV export of your whole list for your own records and budgeting.</p>
  <p><a href="__STRIPE_PRO_LINK__" target="_blank" rel="noopener"><button type="button">Get Premium — $2/month</button></a>
  <a href="/export.csv"><button type="button" class="secondary">Download CSV</button></a></p>
  <p class="muted">CSV export works right now in this version; the Premium checkout link is set in config.py.</p>
</div>

<script>
const $ = id => document.getElementById(id);

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function monthlyOf(s) {
  return s.cycle === 'monthly' ? s.price : s.price / 12;
}

function daysAgo(iso) {
  if (!iso) return null;
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(d)) return null;
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}

async function refresh() {
  const res = await fetch('/api/subs');
  const subs = await res.json();

  const totalMonth = subs.reduce((t, s) => t + monthlyOf(s), 0);
  $('total-month').innerHTML = '$' + totalMonth.toFixed(2) +
    '<span style="font-size:1.2rem"> / month</span>';
  $('total-year').textContent = '$' + (totalMonth * 12).toFixed(2) +
    ' per year · ' + subs.length + (subs.length === 1 ? ' subscription' : ' subscriptions');
  $('share-line').value = "I'm spending $" + totalMonth.toFixed(2) + "/month on AI";

  // Duplicate-provider warning (named providers only; Custom is free-form).
  const counts = {};
  subs.forEach(s => { if (s.provider !== 'Custom') counts[s.provider] = (counts[s.provider] || 0) + 1; });
  const dups = Object.keys(counts).filter(p => counts[p] > 1);
  const warn = $('dup-warn');
  if (dups.length) {
    warn.innerHTML = '<strong>Possible duplicates:</strong> ' +
      dups.map(p => esc(p) + ' appears ' + counts[p] + ' times').join('; ') +
      '. You may be paying twice for the same thing.';
    warn.classList.add('show');
  } else {
    warn.classList.remove('show');
    warn.innerHTML = '';
  }

  // List.
  if (!subs.length) {
    $('list').innerHTML = '<p class="empty">Nothing here yet — add your first subscription above.</p>';
    return;
  }
  let html = '<table><tr><th>Name</th><th>Provider</th><th>Cost</th><th>Last used</th><th></th></tr>';
  subs.forEach(s => {
    const ago = daysAgo(s.last_used);
    const unused = ago !== null && ago > 30;
    const dupBadge = counts[s.provider] > 1 && s.provider !== 'Custom'
      ? '<span class="badge dup">possible duplicate</span>' : '';
    html += '<tr><td>' + esc(s.name) + '</td><td>' + esc(s.provider) + '</td>' +
      '<td>$' + Number(s.price).toFixed(2) + ' / ' + esc(s.cycle) +
      ' ($' + monthlyOf(s).toFixed(2) + '/mo)</td>' +
      '<td>' + (s.last_used ? esc(s.last_used) +
        (unused ? '<span class="badge unused">possibly unused</span>' : '') : '—') + '</td>' +
      '<td><button class="danger" data-del="' + s.id + '">Delete</button></td></tr>';
  });
  html += '</table>';
  $('list').innerHTML = html;
  document.querySelectorAll('[data-del]').forEach(btn => {
    btn.addEventListener('click', async () => {
      await fetch('/api/delete', { method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: Number(btn.dataset.del)}) });
      refresh();
    });
  });
}

$('add-form').addEventListener('submit', async e => {
  e.preventDefault();
  const body = {
    name: $('name').value.trim(),
    provider: $('provider').value,
    price: parseFloat($('price').value),
    cycle: $('cycle').value,
    last_used: $('last-used').value || null,
  };
  const res = await fetch('/api/subs', { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert('Could not add subscription: ' + (err.error || res.status));
    return;
  }
  e.target.reset();
  refresh();
});

$('copy-btn').addEventListener('click', async () => {
  const line = $('share-line');
  line.select();
  try { await navigator.clipboard.writeText(line.value); }
  catch (_) { document.execCommand('copy'); }
  $('copy-btn').textContent = 'Copied!';
  setTimeout(() => $('copy-btn').textContent = 'Copy', 1500);
});

refresh();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- handler

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console clean
        pass

    def _send(self, status, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            page = PAGE.replace("__AD_SLOT_HTML__",
                                 AD_SLOT_HTML if AD_SLOT_HTML else "Ad space")
            page = page.replace("__STRIPE_PRO_LINK__", STRIPE_PRO_LINK)
            self._send(200, page, "text/html; charset=utf-8")
        elif path == "/api/subs":
            with LOCK:
                self._send(200, json.dumps(load_subs()))
        elif path == "/export.csv":
            with LOCK:
                subs = load_subs()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["name", "provider", "price", "billing_cycle",
                        "monthly_equivalent", "last_used"])
            for s in subs:
                w.writerow([s.get("name", ""), s.get("provider", ""),
                            s.get("price", ""), s.get("cycle", ""),
                            round(monthly_equivalent(s), 2),
                            s.get("last_used") or ""])
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition",
                             'attachment; filename="ai-spend.csv"')
            data = buf.getvalue().encode("utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/subs":
            body = self._read_json()
            if not isinstance(body, dict):
                self._send(400, json.dumps({"error": "invalid JSON"}))
                return
            name = str(body.get("name") or "").strip()
            provider = str(body.get("provider") or "")
            cycle = str(body.get("cycle") or "")
            last_used = body.get("last_used") or None
            try:
                price = float(body.get("price"))
            except (TypeError, ValueError):
                price = -1
            if (not name or len(name) > 100 or provider not in PROVIDERS
                    or cycle not in ("monthly", "yearly")
                    or price < 0 or price != price or price == float("inf")):
                self._send(400, json.dumps({"error": "invalid subscription"}))
                return
            if last_used is not None:
                try:
                    date.fromisoformat(str(last_used))
                except ValueError:
                    self._send(400, json.dumps({"error": "bad last_used date"}))
                    return
                last_used = str(last_used)
            with LOCK:
                subs = load_subs()
                sub = {"id": next_id(subs), "name": name, "provider": provider,
                       "price": price, "cycle": cycle, "last_used": last_used}
                subs.append(sub)
                save_subs(subs)
            self._send(201, json.dumps(sub))
        elif path == "/api/delete":
            body = self._read_json()
            if not isinstance(body, dict) or "id" not in body:
                self._send(400, json.dumps({"error": "id required"}))
                return
            with LOCK:
                subs = load_subs()
                kept = [s for s in subs if s.get("id") != body["id"]]
                if len(kept) == len(subs):
                    self._send(404, json.dumps({"error": "not found"}))
                    return
                save_subs(kept)
            self._send(200, json.dumps({"ok": True}))
        else:
            self._send(404, json.dumps({"error": "not found"}))


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"AI Spend Tracker running at http://localhost:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
