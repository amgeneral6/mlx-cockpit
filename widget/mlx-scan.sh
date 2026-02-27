#!/bin/bash
# MLX Server Discovery — scans ports 8080-8090 for MLX servers
# Called by the Übersicht widget every 3 seconds

procs=$(ps ax -o args= 2>/dev/null | grep -E 'mlx_(lm|vlm)\.server' | grep -v grep | grep -v 'bash -c')
echo '{"services":['
first=1
for port in 8080 8081 8082 8083 8084 8085 8086 8087 8088 8089 8090; do
  metrics=$(curl -s --connect-timeout 0.5 --max-time 2 "http://localhost:$port/v1/metrics" 2>/dev/null | tr -d '\n')
  if [ -n "$metrics" ] && echo "$metrics" | grep -q '"summary"'; then
    : # valid metrics response
  else
    health=$(curl -s --connect-timeout 0.5 --max-time 1 "http://localhost:$port/health" 2>/dev/null | tr -d '\n')
    if [ -n "$health" ] && echo "$health" | grep -q '"status"'; then
      hmodel=$(echo "$health" | grep -oE '"model"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"model"[[:space:]]*:[[:space:]]*"//;s/"$//')
      [ -n "$hmodel" ] && metrics=$(printf '{"summary":null,"health_model":"%s"}' "$hmodel") || metrics='{"summary":null}'
    elif nc -z localhost $port 2>/dev/null; then
      echo "$procs" | grep -q -- "--port $port" || continue
      metrics='{"busy":true}'
    else
      continue
    fi
  fi
  proc=$(echo "$procs" | grep -- "--port $port" | head -1)
  model="unknown"; stype="LLM"
  if [ -n "$proc" ]; then
    m=$(echo "$proc" | grep -oE '\-\-model [^ ]+' | head -1 | sed 's/--model //')
    [ -n "$m" ] && model="$m"
    if echo "$proc" | grep -q 'mlx_vlm'; then stype="Vision"
    elif echo "$model" | grep -qi 'vl\|vision'; then stype="Vision"; fi
  fi
  if [ "$model" = "unknown" ]; then
    # Check health_model from fallback metrics
    hm=$(echo "$metrics" | grep -oE '"health_model":"[^"]*"' | sed 's/"health_model":"//;s/"$//')
    [ -n "$hm" ] && model="$hm"
  fi
  if [ "$model" = "unknown" ]; then
    # Try /health endpoint for model name
    hresp=$(curl -s --connect-timeout 0.5 --max-time 1 "http://localhost:$port/health" 2>/dev/null)
    hm=$(echo "$hresp" | grep -oE '"model"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"model"[[:space:]]*:[[:space:]]*"//;s/"$//')
    [ -n "$hm" ] && model="$hm"
  fi
  if [ "$stype" = "LLM" ] && [ "$model" != "unknown" ]; then
    echo "$model" | grep -qi 'vl\|vision' && stype="Vision"
    echo "$model" | grep -qi 'whisper\|stt\|speech' && stype="STT"
  fi
  [ $first -eq 1 ] && first=0 || printf ','
  printf '{"port":%s,"type":"%s","model":"%s","metrics":%s}' "$port" "$stype" "$model" "$metrics"
done
echo ']}'
