"""
mlx_lm_metrics.py  --  Metrics additions for mlx_lm/server.py
=============================================================

This module contains every metrics-related addition that must be patched into
the stock mlx_lm server (mlx_lm/server.py).  Each section is annotated with
the exact insertion point so the changes can be applied manually or with a
script.

Target file: mlx_lm/server.py
Server type: stdlib http.server (BaseHTTPRequestHandler / ThreadingHTTPServer)
"""

# ---------------------------------------------------------------------------
# 1. IMPORT
# ---------------------------------------------------------------------------
# The only extra import needed is `deque` from the collections module.
# In the stock server.py this import already exists on the original line:
#     from collections import deque
# If it is not present, add it to the imports block at the top of the file.

from collections import deque

# ---------------------------------------------------------------------------
# 2. MODULE-LEVEL METRICS STORE
# ---------------------------------------------------------------------------
# INSERT after the top-level imports (after `from .utils import load, sharded_load`)
# and before `def get_system_fingerprint():`.

# Module-level store for recent request metrics (used by /dashboard and /v1/metrics)
_metrics_store: deque = deque(maxlen=200)


# ---------------------------------------------------------------------------
# 3. DASHBOARD HTML
# ---------------------------------------------------------------------------
# INSERT immediately after the _metrics_store declaration above,
# before `def get_system_fingerprint():`.
#
# This is a large multi-line string containing the complete HTML/CSS/JS
# dashboard that auto-discovers MLX servers by scanning ports 8080-8090.
# Falls back to /health for unpatched servers (e.g. Whisper).
#
# The standalone HTML file is saved separately at:
#   mlx-cockpit/dashboard/index.html

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MLX Server Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
         background: #0d1117; color: #c9d1d9; padding: 24px; }
  h1 { color: #58a6ff; margin-bottom: 4px; font-size: 1.5rem; }
  #status { font-size: 0.75rem; color: #3fb950; margin-bottom: 16px; }
  .tabs { display: flex; gap: 4px; margin-bottom: 20px; }
  .tab { padding: 8px 20px; border-radius: 8px 8px 0 0; border: 1px solid #30363d;
         border-bottom: none; background: #161b22; color: #8b949e; cursor: pointer;
         font-size: 0.85rem; font-weight: 600; letter-spacing: 0.03em; transition: all 0.15s; }
  .tab:hover { color: #c9d1d9; background: #1c2128; }
  .tab.active { background: #0d1117; border-bottom: 2px solid #0d1117;
                position: relative; top: 1px; }
  .tab .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
              margin-right: 6px; vertical-align: middle; }
  .dot.on { background: #3fb950; box-shadow: 0 0 6px #3fb950; }
  .dot.off { background: #f85149; box-shadow: 0 0 6px #f85149; }
  .panel { display: none; }
  .panel.active { display: block; }
  .cards { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 16px 24px; min-width: 180px; flex: 1; }
  .card .label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase;
                 letter-spacing: 0.05em; margin-bottom: 4px; }
  .card .value { font-size: 1.6rem; font-weight: 600; }
  table { width: 100%; border-collapse: collapse; background: #161b22;
          border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
  th { background: #21262d; color: #8b949e; font-size: 0.75rem;
       text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 12px;
       text-align: left; }
  td { padding: 8px 12px; border-top: 1px solid #21262d; font-size: 0.85rem; }
  tr:hover td { background: #1c2128; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .muted { color: #8b949e; }
  .offline-msg { text-align: center; padding: 48px 0; color: #484f58; font-size: 0.9rem; }
</style>
</head>
<body>
<h1>MLX Server Dashboard</h1>
<div id="status">Connecting...</div>
<div class="tabs" id="tabs"></div>
<div id="panels"></div>

<script>
var SCAN_PORTS = [8080,8081,8082,8083,8084,8085,8086,8087,8088,8089,8090];
var MODEL_COLORS = ["#58a6ff","#d2a8ff","#3fb950","#f97316","#ec4899"];
var activePort = null;

function switchTab(port) {
  activePort = port;
  document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
  var tab = document.getElementById('tab-' + port);
  var panel = document.getElementById('panel-' + port);
  if (tab) tab.classList.add('active');
  if (panel) panel.classList.add('active');
}

function renderTabs(services) {
  var tabsEl = document.getElementById('tabs');
  tabsEl.innerHTML = '';
  services.forEach(function(svc, i) {
    var color = MODEL_COLORS[i % MODEL_COLORS.length];
    var div = document.createElement('div');
    div.className = 'tab' + (svc.port === activePort ? ' active' : '');
    div.id = 'tab-' + svc.port;
    div.style.color = svc.port === activePort ? color : '';
    div.onclick = function() { switchTab(svc.port); };
    var modelName = 'Port ' + svc.port;
    if (svc.data.requests && svc.data.requests.length > 0) {
      modelName = svc.data.requests[svc.data.requests.length - 1].model.split('/').pop();
    } else if (svc.data.health_model) {
      modelName = svc.data.health_model.split('/').pop();
    }
    div.innerHTML = '<span class="dot on"></span>' + modelName;
    tabsEl.appendChild(div);
  });
}

function renderPanels(services) {
  var panelsEl = document.getElementById('panels');
  panelsEl.innerHTML = '';
  services.forEach(function(svc, i) {
    var color = MODEL_COLORS[i % MODEL_COLORS.length];
    var d = svc.data;
    var div = document.createElement('div');
    div.className = 'panel' + (svc.port === activePort ? ' active' : '');
    div.id = 'panel-' + svc.port;

    var s = d.summary || {};
    var contentHtml = '';

    if (svc.healthOnly) {
      var hModel = d.health_model ? d.health_model : 'Unknown';
      contentHtml += '<div class="cards">';
      contentHtml += '<div class="card"><div class="label">Model</div><div class="value" style="color:' + color + '; font-size:1rem">' + hModel + '</div></div>';
      contentHtml += '<div class="card"><div class="label">Status</div><div class="value" style="color:#3fb950">Online</div></div>';
      contentHtml += '<div class="card"><div class="label">Port</div><div class="value" style="color:' + color + '">' + svc.port + '</div></div>';
      contentHtml += '</div>';
      contentHtml += '<div class="offline-msg">Metrics not available \\u2014 apply the metrics patch to enable detailed stats</div>';
    } else {
      contentHtml += '<div class="cards">';
      contentHtml += '<div class="card"><div class="label">Total Requests</div><div class="value" style="color:' + color + '">' + (s.total_requests || 0) + '</div></div>';
      contentHtml += '<div class="card"><div class="label">Avg Tok/s</div><div class="value" style="color:' + color + '">' + (s.avg_tokens_per_sec ? s.avg_tokens_per_sec.toFixed(2) : '0') + '</div></div>';
      contentHtml += '<div class="card"><div class="label">Total Prompt Tokens</div><div class="value" style="color:' + color + '">' + (s.total_prompt_tokens || 0).toLocaleString() + '</div></div>';
      contentHtml += '<div class="card"><div class="label">Total Completion Tokens</div><div class="value" style="color:' + color + '">' + (s.total_completion_tokens || 0).toLocaleString() + '</div></div>';
      contentHtml += '</div>';

      contentHtml += '<table><thead><tr>';
      contentHtml += '<th>Timestamp</th><th>Model</th><th class="num">Prompt</th>';
      contentHtml += '<th class="num">Completion</th><th class="num">Total</th>';
      contentHtml += '<th class="num">Latency (s)</th><th class="num">Tok/s</th>';
      contentHtml += '</tr></thead><tbody>';
      if (d.requests && d.requests.length > 0) {
        for (var j = d.requests.length - 1; j >= 0; j--) {
          var m = d.requests[j];
          contentHtml += '<tr>';
          contentHtml += '<td class="muted">' + m.timestamp + '</td>';
          contentHtml += '<td>' + m.model + '</td>';
          contentHtml += '<td class="num">' + m.prompt_tokens + '</td>';
          contentHtml += '<td class="num">' + m.completion_tokens + '</td>';
          contentHtml += '<td class="num">' + m.total_tokens + '</td>';
          contentHtml += '<td class="num">' + m.latency + '</td>';
          contentHtml += '<td class="num">' + m.tokens_per_sec + '</td>';
          contentHtml += '</tr>';
        }
      } else {
        contentHtml += '<tr><td colspan="7" class="offline-msg">Waiting for requests...</td></tr>';
      }
      contentHtml += '</tbody></table>';
    }

    div.innerHTML = contentHtml;
    panelsEl.appendChild(div);
  });
}

async function tryMetrics(p) {
  var metricsData = null;
  try {
    var r = await fetch('http://localhost:' + p + '/v1/metrics', { signal: AbortSignal.timeout(1500) });
    var d = await r.json();
    if (d.summary) metricsData = { port: p, data: d, online: true };
  } catch(e) {}
  try {
    var r = await fetch('http://localhost:' + p + '/health', { signal: AbortSignal.timeout(1500) });
    var d = await r.json();
    if (d.status) {
      if (metricsData) {
        metricsData.data.health_model = d.model || null;
        return metricsData;
      }
      return { port: p, data: { summary: null, health_model: d.model || null, requests: [] }, online: true, healthOnly: true };
    }
  } catch(e) {}
  return metricsData;
}

async function refresh() {
  var results = await Promise.all(SCAN_PORTS.map(function(p) { return tryMetrics(p); }));
  var services = results.filter(function(r) { return r !== null; });

  if (services.length === 0) {
    document.getElementById('tabs').innerHTML = '';
    document.getElementById('panels').innerHTML =
      '<div class="offline-msg">No MLX servers detected on ports 8080\\u20138090</div>';
    document.getElementById('status').textContent = 'Scanning...';
    document.getElementById('status').style.color = '#f85149';
    return;
  }

  if (!activePort || !services.find(function(s) { return s.port === activePort; })) {
    activePort = services[0].port;
  }

  renderTabs(services);
  renderPanels(services);
  document.getElementById('status').textContent =
    services.length + ' server' + (services.length > 1 ? 's' : '') + ' detected \\u2022 polling every 2s';
  document.getElementById('status').style.color = '#3fb950';
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 4. METRICS RECORDING IN handle_completion()
# ---------------------------------------------------------------------------
# INSERT inside the `APIHandler.handle_completion()` method, at the very end
# of the method body, right after the response has been fully written and
# flushed (after `self.wfile.flush()`), and before `def completion_usage_response`.
#
# At this point in the method the following variables are available:
#   - start_time  (set at the top of handle_completion via time.perf_counter())
#   - ctx.prompt  (the tokenized prompt list)
#   - tokens      (the list of generated token ids)
#   - self.requested_model (the model name from the request)

def _record_lm_metric_snippet(self, start_time, ctx_prompt, tokens):
    """
    This is NOT a real callable -- it shows the exact code to splice into
    handle_completion() after the final wfile.flush().
    """
    import time, logging

    # Log per-request metrics
    latency = time.perf_counter() - start_time
    prompt_tokens = len(ctx_prompt)
    completion_tokens = len(tokens)
    total_tokens = prompt_tokens + completion_tokens
    tps = completion_tokens / latency if latency > 0 else 0
    logging.info(
        f"prompt={prompt_tokens} completion={completion_tokens} "
        f"total={total_tokens} | latency={latency:.1f}s | {tps:.2f} tok/s"
    )
    _metrics_store.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": self.requested_model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency": round(latency, 2),
        "tokens_per_sec": round(tps, 2),
    })


# ---------------------------------------------------------------------------
# 5. CORS HEADERS  (already present in stock mlx_lm server)
# ---------------------------------------------------------------------------
# The stock mlx_lm server already has a _set_cors_headers() helper that adds:
#     Access-Control-Allow-Origin: *
#     Access-Control-Allow-Methods: *
#     Access-Control-Allow-Headers: *
#
# This is called by _set_completion_headers() and _set_stream_headers(),
# so the /v1/metrics endpoint automatically gets CORS support.  No extra
# changes are needed here.


# ---------------------------------------------------------------------------
# 6. do_GET ROUTE ADDITIONS
# ---------------------------------------------------------------------------
# INSERT two new elif branches in `APIHandler.do_GET()`, after the existing
# `/health` check and before the 404 fallback.
#
# Original do_GET looks like:
#     def do_GET(self):
#         if self.path.startswith("/v1/models"):
#             self.handle_models_request()
#         elif self.path == "/health":
#             self.handle_health_check()
#         else:
#             ...404...
#
# After patching:
#     def do_GET(self):
#         if self.path.startswith("/v1/models"):
#             self.handle_models_request()
#         elif self.path == "/health":
#             self.handle_health_check()
#         elif self.path == "/v1/metrics":        # <-- NEW
#             self.handle_metrics_request()
#         elif self.path == "/dashboard":          # <-- NEW
#             self.handle_dashboard_request()
#         else:
#             ...404...


# ---------------------------------------------------------------------------
# 7. handle_metrics_request() -- new method on APIHandler
# ---------------------------------------------------------------------------
# INSERT as a new method on the APIHandler class, e.g. after do_GET().

def handle_metrics_request(self):
    """Return recent request metrics as JSON."""
    import json
    self._set_completion_headers(200)
    self.end_headers()
    metrics = list(_metrics_store)
    total_requests = len(metrics)
    avg_tps = (
        sum(m["tokens_per_sec"] for m in metrics) / total_requests
        if total_requests > 0
        else 0
    )
    total_prompt = sum(m["prompt_tokens"] for m in metrics)
    total_completion = sum(m["completion_tokens"] for m in metrics)
    data = {
        "requests": metrics,
        "summary": {
            "total_requests": total_requests,
            "avg_tokens_per_sec": round(avg_tps, 2),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
        },
    }
    self.wfile.write(json.dumps(data).encode())
    self.wfile.flush()


# ---------------------------------------------------------------------------
# 8. handle_dashboard_request() -- new method on APIHandler
# ---------------------------------------------------------------------------
# INSERT as a new method on the APIHandler class, right after
# handle_metrics_request().

def handle_dashboard_request(self):
    """Serve a live HTML dashboard that polls /v1/metrics."""
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.end_headers()
    html = _DASHBOARD_HTML
    self.wfile.write(html.encode())
    self.wfile.flush()
