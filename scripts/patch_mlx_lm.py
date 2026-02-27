#!/usr/bin/env python3
"""
patch_mlx_lm.py — Patch mlx_lm/server.py with /v1/metrics and /dashboard endpoints.

Usage:
    python3 patch_mlx_lm.py <path-to-mlx_lm-server.py>
    python3 patch_mlx_lm.py                               # auto-discovers via import

Creates a .bak backup before modifying. Idempotent: skips if already patched.
Validates all insertions succeeded; rolls back on failure.
"""

import os
import shutil
import sys


def find_server_py():
    """Auto-discover mlx_lm/server.py via import."""
    try:
        import mlx_lm
        return os.path.join(os.path.dirname(mlx_lm.__file__), "server.py")
    except ImportError:
        return None


def load_dashboard_html():
    """Load dashboard/index.html from the project tree."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(script_dir, "..", "dashboard", "index.html")
    with open(html_path, "r") as f:
        return f.read()


def patch(server_path):
    with open(server_path, "r") as f:
        code = f.read()

    # --- Idempotent check ---
    if "_metrics_store" in code:
        print(f"Already patched: {server_path}")
        return True

    # --- Create backup ---
    backup_path = server_path + ".bak"
    shutil.copy2(server_path, backup_path)
    print(f"Backup created: {backup_path}")

    original = code
    insertions = 0

    # ---------------------------------------------------------------
    # 1. Insert _metrics_store + _DASHBOARD_HTML after imports
    # ---------------------------------------------------------------
    # Anchor: "from .utils import load" line (last import in stock server)
    anchor_import = "from .utils import load"
    idx = code.find(anchor_import)
    if idx == -1:
        print("ERROR: Could not find import anchor 'from .utils import load'")
        _rollback(server_path, backup_path)
        return False

    # Find end of that line
    eol = code.index("\n", idx)

    dashboard_html = load_dashboard_html().replace('\\', '\\\\').replace('"""', '\\"\\"\\"')

    metrics_block = (
        "\n\n"
        "# Module-level store for recent request metrics (used by /dashboard and /v1/metrics)\n"
        "_metrics_store: deque = deque(maxlen=200)\n"
        "\n"
        '_DASHBOARD_HTML = """' + dashboard_html + '"""\n'
    )

    code = code[:eol + 1] + metrics_block + code[eol + 1:]
    insertions += 1
    print("  [1/4] Inserted _metrics_store + _DASHBOARD_HTML after imports")

    # ---------------------------------------------------------------
    # 2. Insert metrics recording at end of handle_completion()
    # ---------------------------------------------------------------
    # Anchor: last "self.wfile.flush()" before "def completion_usage_response"
    # We look for the pattern where the response is flushed at the end of
    # handle_completion — this is the last wfile.flush() before
    # completion_usage_response.
    anchor_usage = "def completion_usage_response"
    idx_usage = code.find(anchor_usage)
    if idx_usage == -1:
        print("ERROR: Could not find 'def completion_usage_response'")
        _rollback(server_path, backup_path)
        return False

    # Find the last "self.wfile.flush()" before completion_usage_response
    search_region = code[:idx_usage]
    last_flush = search_region.rfind("self.wfile.flush()")
    if last_flush == -1:
        print("ERROR: Could not find final wfile.flush() in handle_completion")
        _rollback(server_path, backup_path)
        return False

    eol_flush = code.index("\n", last_flush)

    metrics_snippet = '''

        # Log per-request metrics
        latency = time.perf_counter() - start_time
        prompt_tokens = len(ctx.prompt)
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
'''

    code = code[:eol_flush + 1] + metrics_snippet + code[eol_flush + 1:]
    insertions += 1
    print("  [2/4] Inserted metrics recording in handle_completion()")

    # ---------------------------------------------------------------
    # 3. Insert /v1/metrics and /dashboard routes in do_GET()
    # ---------------------------------------------------------------
    # Find the else/404 block in do_GET and insert before it
    # Pattern: '        elif self.path == "/health":\n            self.handle_health_check()\n        else:'
    anchor_get = 'self.handle_health_check()\n        else:'
    idx_get = code.find(anchor_get)
    if idx_get == -1:
        print("ERROR: Could not find do_GET health/else pattern")
        _rollback(server_path, backup_path)
        return False

    insert_pos = idx_get + len("self.handle_health_check()\n")

    route_snippet = (
        '        elif self.path == "/v1/metrics":\n'
        '            self.handle_metrics_request()\n'
        '        elif self.path == "/dashboard":\n'
        '            self.handle_dashboard_request()\n'
    )

    code = code[:insert_pos] + route_snippet + code[insert_pos:]
    insertions += 1
    print("  [3/4] Inserted /v1/metrics and /dashboard routes in do_GET()")

    # ---------------------------------------------------------------
    # 4. Insert handle_metrics_request() and handle_dashboard_request()
    # ---------------------------------------------------------------
    # Insert after do_GET method — find "def handle_health_check"
    anchor_health = "def handle_health_check(self):"
    idx_health = code.find(anchor_health)
    if idx_health == -1:
        print("ERROR: Could not find 'def handle_health_check'")
        _rollback(server_path, backup_path)
        return False

    # Insert before handle_health_check
    methods_snippet = '''    def handle_metrics_request(self):
        """Return recent request metrics as JSON."""
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

    def handle_dashboard_request(self):
        """Serve a live HTML dashboard that polls /v1/metrics."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = _DASHBOARD_HTML
        self.wfile.write(html.encode())
        self.wfile.flush()

    '''

    code = code[:idx_health] + methods_snippet + code[idx_health:]
    insertions += 1
    print("  [4/4] Inserted handle_metrics_request() and handle_dashboard_request()")

    # ---------------------------------------------------------------
    # Validate
    # ---------------------------------------------------------------
    if insertions != 4:
        print(f"ERROR: Expected 4 insertions, got {insertions}. Rolling back.")
        _rollback(server_path, backup_path)
        return False

    # Final sanity checks
    checks = [
        ("_metrics_store", "_metrics_store declaration"),
        ("_DASHBOARD_HTML", "dashboard HTML string"),
        ("handle_metrics_request", "metrics request handler"),
        ("handle_dashboard_request", "dashboard request handler"),
        ('"/v1/metrics"', "/v1/metrics route"),
        ('"/dashboard"', "/dashboard route"),
    ]
    for needle, label in checks:
        if needle not in code:
            print(f"ERROR: Validation failed — missing {label}. Rolling back.")
            _rollback(server_path, backup_path)
            return False

    with open(server_path, "w") as f:
        f.write(code)

    print(f"Patched successfully: {server_path}")
    return True


def _rollback(server_path, backup_path):
    """Restore backup on failure."""
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, server_path)
        print(f"Rolled back to backup: {backup_path}")


def main():
    if len(sys.argv) > 1:
        server_path = sys.argv[1]
    else:
        server_path = find_server_py()
        if not server_path:
            print("ERROR: Could not find mlx_lm/server.py. Pass the path as an argument.")
            sys.exit(1)

    if not os.path.isfile(server_path):
        print(f"ERROR: File not found: {server_path}")
        sys.exit(1)

    print(f"Patching: {server_path}")
    if not patch(server_path):
        sys.exit(1)


if __name__ == "__main__":
    main()
