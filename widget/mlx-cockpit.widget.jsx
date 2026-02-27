// MLX Server Stats — Multi-Model Speedometer Widget
// Auto-discovers running MLX servers via process scanning every 3 seconds

import { run } from "uebersicht";

export const refreshFrequency = 3000;

// --- Theme Presets ---
const THEMES = {
  default: { name: "Default", modelColors: ["#58a6ff", "#d2a8ff", "#3fb950", "#f97316", "#ec4899"], latencyColor: "#f0883e", bg: "rgba(18, 18, 28, 0.88)" },
  cyberpunk: { name: "Cyberpunk", modelColors: ["#ff2a6d", "#05d9e8", "#f9f871", "#ff6b6b", "#a855f7"], latencyColor: "#f9f871", bg: "rgba(10, 10, 20, 0.92)" },
  matrix: { name: "Matrix", modelColors: ["#00ff41", "#39ff14", "#20c20e", "#7fff00", "#00fa9a"], latencyColor: "#20c20e", bg: "rgba(5, 10, 5, 0.92)" },
  ocean: { name: "Ocean", modelColors: ["#0ea5e9", "#7dd3fc", "#06b6d4", "#38bdf8", "#a78bfa"], latencyColor: "#fb923c", bg: "rgba(8, 15, 30, 0.92)" },
  sunset: { name: "Sunset", modelColors: ["#f97316", "#fb7185", "#fbbf24", "#f43f5e", "#a78bfa"], latencyColor: "#fbbf24", bg: "rgba(25, 15, 12, 0.92)" },
};

const getTheme = () => {
  try {
    const key = localStorage.getItem("mlx-cockpit-theme");
    if (key && THEMES[key]) return { ...THEMES[key], key };
  } catch (e) {}
  return { ...THEMES.default, key: "default" };
};

// Flag shared between init() drag handling and click handling
let _wasDrag = false;

// Discovery script scans ports 8080-8090 for /v1/metrics and /health endpoints
// Enriches with process info for model name and type (LLM/Vision/STT)
export const command = `__MLX_SCAN_PATH__`;

export const className = `
  top: 16px;
  left: calc(100% - 580px);
  z-index: 999;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif;
  -webkit-font-smoothing: antialiased;
  cursor: grab;
  user-select: none;
`;

// Draggable + click-to-open-dashboard — all via native events.
// Guard ensures listeners are registered exactly once, even if init() is called repeatedly.
export const init = (dispatch) => {
  if (window._mlxInitDone) return;
  window._mlxInitDone = true;

  let isDragging = false;
  let didDrag = false;
  let startX, startY, origX, origY;

  document.addEventListener("mousedown", (e) => {
    const el = document.querySelector('[id*="mlx-server-stats"]');
    if (!el || !el.contains(e.target)) return;
    isDragging = true;
    didDrag = false;
    const rect = el.getBoundingClientRect();
    startX = e.clientX;
    startY = e.clientY;
    origX = rect.left;
    origY = rect.top;
    el.style.cursor = "grabbing";
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) didDrag = true;
    const el = document.querySelector('[id*="mlx-server-stats"]');
    if (!el) return;
    el.style.left = (origX + dx) + "px";
    el.style.top = (origY + dy) + "px";
    el.style.right = "auto";
  });

  document.addEventListener("mouseup", () => {
    if (!isDragging) return;
    isDragging = false;
    _wasDrag = didDrag;
    const el = document.querySelector('[id*="mlx-server-stats"]');
    if (el) el.style.cursor = "grab";
  });

  document.addEventListener("click", (e) => {
    const el = document.querySelector('[id*="mlx-server-stats"]');
    if (!el || !el.contains(e.target)) return;
    if (_wasDrag) { _wasDrag = false; return; }
    // Open dashboard on first discovered port (stored by render)
    const port = window._mlxFirstPort || 8080;
    run(`open http://localhost:${port}/dashboard`);
  });
};

// --- SVG Arc Gauge ---
const polarToCartesian = (cx, cy, r, deg) => {
  const rad = ((deg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
};

const describeArc = (cx, cy, r, startAngle, endAngle) => {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
};

const Gauge = ({ value, max, size, label, unit, color }) => {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 10;
  const startAngle = 150;
  const endAngle = 390;
  const totalArc = endAngle - startAngle;
  const clamped = Math.min(Math.max(value, 0), max);
  const valueAngle = startAngle + (clamped / max) * totalArc;

  const ticks = [];
  const tickCount = 8;
  for (let i = 0; i <= tickCount; i++) {
    const angle = startAngle + (i / tickCount) * totalArc;
    const outer = polarToCartesian(cx, cy, r, angle);
    const isMajor = i % 2 === 0;
    const inner = polarToCartesian(cx, cy, r - (isMajor ? 8 : 5), angle);
    ticks.push(
      <line key={i} x1={outer.x} y1={outer.y} x2={inner.x} y2={inner.y}
        stroke={isMajor ? "rgba(255,255,255,0.35)" : "rgba(255,255,255,0.15)"}
        strokeWidth={isMajor ? 1.5 : 1} strokeLinecap="round" />
    );
    if (isMajor) {
      const labelPos = polarToCartesian(cx, cy, r - 16, angle);
      ticks.push(
        <text key={`l${i}`} x={labelPos.x} y={labelPos.y} fill="rgba(255,255,255,0.3)"
          fontSize="7" textAnchor="middle" dominantBaseline="middle">
          {Math.round((i / tickCount) * max)}
        </text>
      );
    }
  }

  const needleTip = polarToCartesian(cx, cy, r - 12, valueAngle);
  const needleBase1 = polarToCartesian(cx, cy, 3, valueAngle - 90);
  const needleBase2 = polarToCartesian(cx, cy, 3, valueAngle + 90);

  return (
    <div style={{ textAlign: "center", position: "relative" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          <linearGradient id={`grad-${label}`} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={color} stopOpacity="0.2" />
            <stop offset="100%" stopColor={color} stopOpacity="1" />
          </linearGradient>
          <filter id={`glow-${label}`}>
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <path d={describeArc(cx, cy, r, startAngle, endAngle)}
          fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="6" strokeLinecap="round" />
        {value > 0 && (
          <path d={describeArc(cx, cy, r, startAngle, valueAngle)}
            fill="none" stroke={`url(#grad-${label})`} strokeWidth="6" strokeLinecap="round"
            filter={`url(#glow-${label})`} />
        )}
        {ticks}
        <polygon
          points={`${needleTip.x},${needleTip.y} ${needleBase1.x},${needleBase1.y} ${needleBase2.x},${needleBase2.y}`}
          fill={color} opacity="0.9" />
        <circle cx={cx} cy={cy} r="4" fill="#1a1a2e" stroke={color} strokeWidth="1.5" />
        <text x={cx} y={cy + 18} fill="white" fontSize="18" fontWeight="600"
          textAnchor="middle" dominantBaseline="middle"
          style={{ fontVariantNumeric: "tabular-nums" }}>
          {typeof value === "number" ? value.toFixed(1) : value}
        </text>
        <text x={cx} y={cy + 30} fill="rgba(255,255,255,0.4)" fontSize="8"
          textAnchor="middle" dominantBaseline="middle" textTransform="uppercase"
          letterSpacing="0.08em">
          {unit}
        </text>
      </svg>
      <div style={{ fontSize: "9px", color: "rgba(255,255,255,0.45)", marginTop: "-8px",
        textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</div>
    </div>
  );
};

const Pill = ({ label, value, icon }) => (
  <div style={{
    display: "flex", alignItems: "center", gap: "6px",
    background: "rgba(255,255,255,0.04)", borderRadius: "8px",
    padding: "6px 10px", border: "1px solid rgba(255,255,255,0.06)",
  }}>
    <span style={{ fontSize: "12px" }}>{icon}</span>
    <div>
      <div style={{ fontSize: "8px", color: "rgba(255,255,255,0.35)",
        textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
      <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.9)",
        fontWeight: 500, fontVariantNumeric: "tabular-nums", marginTop: "1px" }}>{value}</div>
    </div>
  </div>
);

// --- Model Section ---
const ModelSection = ({ title, color, latencyColor, dotColor, modelName, online, busy, tps, latencyVal, summary, tag }) => {
  const tpsMax = Math.max(20, Math.ceil((tps || 0) / 10) * 10 + 10);
  const latMax = Math.max(5, Math.ceil(latencyVal || 0) + 2);

  return (
    <div style={{ flex: 1, minWidth: "240px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
        <div style={{
          width: "7px", height: "7px", borderRadius: "50%",
          background: dotColor, boxShadow: `0 0 8px ${dotColor}`,
        }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "10px", color: "rgba(255,255,255,0.5)",
            textTransform: "uppercase", letterSpacing: "0.12em", fontWeight: 600 }}>
            {modelName}
          </div>
        </div>
        <div style={{
          fontSize: "8px", color: color, background: `${color}15`,
          padding: "2px 6px", borderRadius: "4px", fontWeight: 600,
          textTransform: "uppercase", letterSpacing: "0.08em",
        }}>{tag}</div>
      </div>

      {online && summary && tps !== undefined ? (
        <div>
          <div style={{ display: "flex", justifyContent: "center", gap: "4px" }}>
            <Gauge value={tps} max={tpsMax} size={115} label="Speed" unit="tok/s" color={color} />
            <Gauge value={latencyVal} max={latMax} size={115} label="Latency" unit="seconds" color={latencyColor || "#f0883e"} />
          </div>
          <div style={{ display: "flex", gap: "4px", marginTop: "8px" }}>
            <Pill icon={"+"} label="Requests" value={summary.total_requests} />
            <Pill icon={">"} label="Prompt" value={summary.total_prompt_tokens.toLocaleString()} />
            <Pill icon={"<"} label="Output" value={summary.total_completion_tokens.toLocaleString()} />
          </div>
        </div>
      ) : online ? (
        <div style={{ textAlign: "center", padding: "16px 0", color: "rgba(255,255,255,0.3)",
          fontSize: "11px" }}>Ready — waiting for requests</div>
      ) : busy ? (
        <div style={{ textAlign: "center", padding: "16px 0", color: latencyColor || "#f0883e",
          fontSize: "11px" }}>Generating...</div>
      ) : (
        <div style={{ textAlign: "center", padding: "16px 0", color: "rgba(255,255,255,0.2)",
          fontSize: "11px" }}>Offline</div>
      )}
    </div>
  );
};

export const render = ({ output }) => {
  let data;
  try {
    data = JSON.parse(output);
  } catch (e) {
    data = {};
  }

  const theme = getTheme();

  // Build services array from discovered servers
  const services = (data.services || []).map((svc, i) => {
    const m = svc.metrics || {};
    const hasMetrics = m.summary != null && m.summary !== null;
    const online = hasMetrics || m.health_model != null;
    const busy = !online && m.busy === true;
    const latest = hasMetrics && m.requests && m.requests.length > 0
      ? m.requests[m.requests.length - 1] : null;
    const modelName = latest ? latest.model.split("/").pop()
      : (svc.model && svc.model !== "unknown" ? svc.model.split("/").pop() : `Port ${svc.port}`);
    return {
      ...svc,
      color: theme.modelColors[i % theme.modelColors.length],
      online,
      busy,
      hasMetrics,
      modelName,
      tps: hasMetrics ? m.summary.avg_tokens_per_sec : 0,
      latency: latest ? latest.latency : 0,
      summary: hasMetrics ? m.summary : null,
    };
  });

  // Store first port for click-to-open-dashboard
  if (services.length > 0) {
    window._mlxFirstPort = services[0].port;
  }

  const containerBase = {
    position: "relative",
    background: theme.bg,
    backdropFilter: "blur(24px)",
    WebkitBackdropFilter: "blur(24px)",
    borderRadius: "20px",
    border: "1px solid rgba(255, 255, 255, 0.06)",
    boxShadow: "0 8px 32px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255,255,255,0.04)",
    padding: "16px 20px",
  };

  // All offline / no services discovered
  const anyAlive = services.some(s => s.online || s.busy);
  if (services.length === 0 || !anyAlive) {
    return (
      <div style={{ ...containerBase, textAlign: "center", padding: "24px" }}>
        <div style={{ fontSize: "24px", marginBottom: "8px", opacity: 0.3 }}>{"."}</div>
        <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.3)",
          textTransform: "uppercase", letterSpacing: "0.1em" }}>MLX Servers Offline</div>
      </div>
    );
  }

  return (
    <div style={containerBase}>
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
        {services.map((svc, i) => (
          <div key={svc.port} style={{ display: "contents" }}>
            {i > 0 && (
              <div style={{ width: "1px", background: "rgba(255,255,255,0.08)", alignSelf: "stretch" }} />
            )}
            <ModelSection
              title={svc.type}
              tag={svc.type}
              color={svc.color}
              latencyColor={theme.latencyColor}
              dotColor={svc.online || svc.busy ? "#3fb950" : "#f85149"}
              modelName={svc.modelName}
              online={svc.online}
              busy={svc.busy}
              tps={svc.tps}
              latencyVal={svc.latency}
              summary={svc.summary}
            />
          </div>
        ))}
      </div>
    </div>
  );
};
