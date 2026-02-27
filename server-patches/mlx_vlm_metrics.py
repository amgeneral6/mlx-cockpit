"""
mlx_vlm_metrics.py  --  Metrics additions for mlx_vlm/server.py
================================================================

This module contains every metrics-related addition that must be patched into
the stock mlx_vlm server (mlx_vlm/server.py).  Each section is annotated with
the exact insertion point so the changes can be applied manually or with a
script.

Target file: mlx_vlm/server.py
Server type: FastAPI + Uvicorn (async)
"""

# ---------------------------------------------------------------------------
# 1. IMPORTS
# ---------------------------------------------------------------------------
# The following imports are required by the metrics additions.
# In the stock server.py these already exist; verify they are present at the
# top of the file:
#
#   import time
#   from collections import deque
#   from fastapi.middleware.cors import CORSMiddleware

import time
from collections import deque


# ---------------------------------------------------------------------------
# 2. CORS MIDDLEWARE
# ---------------------------------------------------------------------------
# INSERT right after the `app = FastAPI(...)` declaration.
#
# This enables cross-origin GET requests so the dashboard (served from the
# mlx_lm server on port 8080) can fetch /v1/metrics from the mlx_vlm server
# on port 8081.
#
# Code to add:
#
#   app.add_middleware(
#       CORSMiddleware,
#       allow_origins=["*"],
#       allow_methods=["GET"],
#       allow_headers=["*"],
#   )
#
# Note: Only GET is allowed, keeping the security surface minimal.


# ---------------------------------------------------------------------------
# 3. MODULE-LEVEL METRICS STORE AND RECORDING FUNCTION
# ---------------------------------------------------------------------------
# INSERT after the CORS middleware block and after `model_cache = {}`,
# before the first class/function definition (e.g. before FlexibleBaseModel
# or load_model_resources).

# --- Metrics store (mirrors mlx_lm server format) ---
_vlm_metrics_store: deque = deque(maxlen=200)


def _record_vlm_metric(model, prompt_tokens, completion_tokens, latency, tokens_per_sec):
    """Append one request's metrics to the in-memory ring buffer."""
    _vlm_metrics_store.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": (model.split("/")[-1] if model else "unknown"),
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int((prompt_tokens or 0) + (completion_tokens or 0)),
        "latency": round(latency, 2),
        "tokens_per_sec": round(tokens_per_sec or 0, 2),
    })


# ---------------------------------------------------------------------------
# 4. METRICS RECORDING IN /responses ENDPOINT (streaming path)
# ---------------------------------------------------------------------------
# INSERT inside the `POST /responses` endpoint's streaming path, right after
# the stream generation loop ends (after the last chunk has been yielded), and
# before the "response.output_text.done" event is sent.
#
# The code reads timing info from the final chunk object (_last_chunk) and
# the start time (_resp_stream_start) that was captured at the beginning of
# the streaming generator.
#
# Snippet (inside the async stream_generator):
#
#     # Record metrics from final chunk
#     if _last_chunk is not None:
#         _record_vlm_metric(
#             openai_request.model,
#             getattr(_last_chunk, "prompt_tokens", 0),
#             getattr(_last_chunk, "generation_tokens", 0),
#             time.time() - _resp_stream_start,
#             getattr(_last_chunk, "generation_tps", 0),
#         )


# ---------------------------------------------------------------------------
# 5. METRICS RECORDING IN /responses ENDPOINT (non-streaming path)
# ---------------------------------------------------------------------------
# INSERT inside the `POST /responses` endpoint's non-streaming path, right
# after `gc.collect()` and the "Generation finished" print, before building
# the OpenAIResponse object.
#
# Variables available at insertion point:
#   - openai_request.model  (model name from request)
#   - result.prompt_tokens
#   - result.generation_tokens
#   - _resp_latency         (time.time() - _resp_start)
#   - result.generation_tps
#
# Snippet:
#
#     _record_vlm_metric(
#         openai_request.model,
#         result.prompt_tokens,
#         result.generation_tokens,
#         _resp_latency,
#         result.generation_tps,
#     )


# ---------------------------------------------------------------------------
# 6. METRICS RECORDING IN /chat/completions ENDPOINT (streaming path)
# ---------------------------------------------------------------------------
# INSERT inside the `POST /chat/completions` endpoint's streaming path,
# after the stream generation for-loop finishes and before the final
# "stop" chunk is sent.
#
# Variables available at insertion point:
#   - request.model         (model name from request)
#   - usage_stats           (dict with "input_tokens", "output_tokens", etc.)
#   - _stream_start         (time.time() captured at beginning of generator)
#   - usage_stats["generation_tps"]
#
# Snippet:
#
#     # Record metrics from final chunk
#     _record_vlm_metric(
#         request.model,
#         usage_stats.get("input_tokens", 0),
#         usage_stats.get("output_tokens", 0),
#         time.time() - _stream_start,
#         usage_stats.get("generation_tps", 0),
#     )


# ---------------------------------------------------------------------------
# 7. METRICS RECORDING IN /chat/completions ENDPOINT (non-streaming path)
# ---------------------------------------------------------------------------
# INSERT inside the `POST /chat/completions` endpoint's non-streaming path,
# after `gc.collect()` and the "Generation finished" print, before building
# the usage_stats / response objects.
#
# Variables available at insertion point:
#   - request.model
#   - gen_result.prompt_tokens
#   - gen_result.generation_tokens
#   - _gen_latency           (time.time() - _gen_start)
#   - gen_result.generation_tps
#
# Snippet:
#
#     _record_vlm_metric(
#         request.model,
#         gen_result.prompt_tokens,
#         gen_result.generation_tokens,
#         _gen_latency,
#         gen_result.generation_tps,
#     )


# ---------------------------------------------------------------------------
# 8. /v1/metrics ENDPOINT
# ---------------------------------------------------------------------------
# INSERT as a new FastAPI route, after the /health endpoint and before
# the /unload endpoint (or at any convenient location among the route
# definitions).

async def metrics_endpoint():
    """
    Return recent request metrics and summary (same format as mlx_lm server).

    Register with:  @app.get("/v1/metrics")
    """
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
