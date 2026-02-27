#!/usr/bin/env python3
"""
patch_mlx_vlm.py — Patch mlx_vlm/server.py with /v1/metrics endpoint.

Usage:
    python3 patch_mlx_vlm.py <path-to-mlx_vlm-server.py>
    python3 patch_mlx_vlm.py                                # auto-discovers via import

Creates a .bak backup before modifying. Idempotent: skips if already patched.
Validates all insertions succeeded; rolls back on failure.
"""

import os
import shutil
import sys


def find_server_py():
    """Auto-discover mlx_vlm/server.py via import."""
    try:
        import mlx_vlm
        return os.path.join(os.path.dirname(mlx_vlm.__file__), "server.py")
    except ImportError:
        return None


def patch(server_path):
    with open(server_path, "r") as f:
        code = f.read()

    # --- Idempotent check ---
    if "_vlm_metrics_store" in code:
        print(f"Already patched: {server_path}")
        return True

    # --- Create backup ---
    backup_path = server_path + ".bak"
    shutil.copy2(server_path, backup_path)
    print(f"Backup created: {backup_path}")

    insertions = 0

    # ---------------------------------------------------------------
    # 1. Ensure CORSMiddleware import exists
    # ---------------------------------------------------------------
    if "from fastapi.middleware.cors import CORSMiddleware" not in code:
        # Insert after "from fastapi" line
        anchor = "from fastapi import"
        idx = code.find(anchor)
        if idx == -1:
            print("ERROR: Could not find 'from fastapi import'")
            _rollback(server_path, backup_path)
            return False
        eol = code.index("\n", idx)
        code = code[:eol + 1] + "from fastapi.middleware.cors import CORSMiddleware\n" + code[eol + 1:]
        print("  Inserted CORSMiddleware import")

    # ---------------------------------------------------------------
    # 2. Insert CORS middleware after app = FastAPI(...)
    # ---------------------------------------------------------------
    if "app.add_middleware" not in code:
        # Find end of app = FastAPI(...) block
        anchor_app = "app = FastAPI("
        idx_app = code.find(anchor_app)
        if idx_app == -1:
            print("ERROR: Could not find 'app = FastAPI('")
            _rollback(server_path, backup_path)
            return False

        # Find the closing paren of FastAPI(...)
        # Look for the line starting with ")" after app = FastAPI(
        search_start = idx_app
        paren_depth = 0
        i = code.index("(", search_start)
        for i in range(i, len(code)):
            if code[i] == "(":
                paren_depth += 1
            elif code[i] == ")":
                paren_depth -= 1
                if paren_depth == 0:
                    break
        eol_app = code.index("\n", i)

        cors_snippet = (
            "\n"
            "app.add_middleware(\n"
            '    CORSMiddleware,\n'
            '    allow_origins=["*"],\n'
            '    allow_methods=["GET"],\n'
            '    allow_headers=["*"],\n'
            ")\n"
        )
        code = code[:eol_app + 1] + cors_snippet + code[eol_app + 1:]
        insertions += 1
        print("  [1/3] Inserted CORS middleware")
    else:
        insertions += 1
        print("  [1/3] CORS middleware already present")

    # ---------------------------------------------------------------
    # 3. Insert metrics store + recording function after model_cache
    # ---------------------------------------------------------------
    anchor_cache = "model_cache = {}"
    idx_cache = code.find(anchor_cache)
    if idx_cache == -1:
        # Try alternate patterns
        anchor_cache = "model_cache: "
        idx_cache = code.find(anchor_cache)
    if idx_cache == -1:
        print("ERROR: Could not find 'model_cache' declaration")
        _rollback(server_path, backup_path)
        return False

    eol_cache = code.index("\n", idx_cache)

    store_snippet = '''

# --- Metrics store (mirrors mlx_lm server format) ---
_vlm_metrics_store: deque = deque(maxlen=200)


def _record_vlm_metric(model, prompt_tokens, completion_tokens, latency, tokens_per_sec):
    _vlm_metrics_store.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": (model.split("/")[-1] if model else "unknown"),
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int((prompt_tokens or 0) + (completion_tokens or 0)),
        "latency": round(latency, 2),
        "tokens_per_sec": round(tokens_per_sec or 0, 2),
    })
'''
    code = code[:eol_cache + 1] + store_snippet + code[eol_cache + 1:]
    insertions += 1
    print("  [2/3] Inserted _vlm_metrics_store + _record_vlm_metric()")

    # ---------------------------------------------------------------
    # 4. Insert /v1/metrics endpoint
    # ---------------------------------------------------------------
    # Find @app.get("/health") or @app.get("/unload") as anchor
    anchor_route = '@app.get("/health")'
    idx_route = code.find(anchor_route)
    if idx_route == -1:
        # Try finding any @app route to insert before
        anchor_route = '@app.post("/unload")'
        idx_route = code.find(anchor_route)
    if idx_route == -1:
        # Fallback: insert before "if __name__"
        anchor_route = 'if __name__'
        idx_route = code.find(anchor_route)

    if idx_route == -1:
        print("ERROR: Could not find insertion point for /v1/metrics route")
        _rollback(server_path, backup_path)
        return False

    metrics_route = '''
@app.get("/v1/metrics")
async def metrics_endpoint():
    """Return recent request metrics and summary."""
    requests_list = list(_vlm_metrics_store)
    total = len(requests_list)
    if total > 0:
        avg_tps = sum(r["tokens_per_sec"] for r in requests_list) / total
        total_prompt = sum(r["prompt_tokens"] for r in requests_list)
        total_completion = sum(r["completion_tokens"] for r in requests_list)
    else:
        avg_tps = 0
        total_prompt = 0
        total_completion = 0
    return {
        "requests": requests_list,
        "summary": {
            "total_requests": total,
            "avg_tokens_per_sec": round(avg_tps, 2),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
        },
    }


'''
    code = code[:idx_route] + metrics_route + code[idx_route:]
    insertions += 1
    print("  [3/3] Inserted /v1/metrics endpoint")

    # ---------------------------------------------------------------
    # Validate
    # ---------------------------------------------------------------
    if insertions != 3:
        print(f"ERROR: Expected 3 insertions, got {insertions}. Rolling back.")
        _rollback(server_path, backup_path)
        return False

    checks = [
        ("_vlm_metrics_store", "metrics store"),
        ("_record_vlm_metric", "recording function"),
        ("/v1/metrics", "metrics route"),
        ("CORSMiddleware", "CORS middleware"),
    ]
    for needle, label in checks:
        if needle not in code:
            print(f"ERROR: Validation failed — missing {label}. Rolling back.")
            _rollback(server_path, backup_path)
            return False

    with open(server_path, "w") as f:
        f.write(code)

    print(f"Patched successfully: {server_path}")
    print()
    print("NOTE: To record per-request metrics, you also need to add")
    print("_record_vlm_metric() calls in the /responses and /chat/completions")
    print("endpoints. See server-patches/mlx_vlm_metrics.py for the exact")
    print("insertion points (sections 4-7).")
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
            print("ERROR: Could not find mlx_vlm/server.py. Pass the path as an argument.")
            sys.exit(1)

    if not os.path.isfile(server_path):
        print(f"ERROR: File not found: {server_path}")
        sys.exit(1)

    print(f"Patching: {server_path}")
    if not patch(server_path):
        sys.exit(1)


if __name__ == "__main__":
    main()
