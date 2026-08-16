// Tides card - a minimal wave showing current tide level, the next
// high/low, and sunrise/sunset, all read off one timeline.

const WIDTH = 600;
const HEIGHT = 200;
const PAD_X = 18;
const PAD_TOP = 54;
const PAD_BOTTOM = 30;
const PLOT_TOP = PAD_TOP;
const PLOT_BOTTOM = HEIGHT - PAD_BOTTOM;
const AMPLITUDE_MARGIN = 1.25;

const NIGHT_SKY = "#0e1330";
const DAY_SKY = "#4f7c96";
const WATER_TOP = "#2f9cc4";
const WATER_BOTTOM = "#06253a";
const WAVE_LINE = "#bdeeff";
const SUN_COLOR = "#f7b955";
const NOW_COLOR = "#f4fbff";
const RISING_COLOR = "#6bd9ac";
const FALLING_COLOR = "#e98a72";

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function mapX(t, windowStart, windowEnd) {
  const frac = (t - windowStart) / (windowEnd - windowStart);
  return PAD_X + clamp(frac, 0, 1) * (WIDTH - 2 * PAD_X);
}

function mapY(height, amplitude) {
  const half = (amplitude / 2) * AMPLITUDE_MARGIN;
  const frac = (height + half) / (2 * half);
  return PLOT_BOTTOM - clamp(frac, 0, 1) * (PLOT_BOTTOM - PLOT_TOP);
}

function smoothPath(points) {
  if (points.length < 2) return "";
  let d = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i === 0 ? 0 : i - 1];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2 < points.length ? i + 2 : i + 1];
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }
  return d;
}

function findLocalExtrema(points) {
  const events = [];
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1].h;
    const cur = points[i].h;
    const next = points[i + 1].h;
    if (cur >= prev && cur >= next && cur > points[i - 1].h - 1e-9) {
      events.push({ kind: "high", point: points[i] });
    } else if (cur <= prev && cur <= next) {
      events.push({ kind: "low", point: points[i] });
    }
  }
  // Drop duplicate/adjacent detections from flat runs.
  return events.filter((e, i) => i === 0 || e.kind !== events[i - 1].kind);
}

function interpolateHeight(points, t) {
  if (!points.length) return 0;
  if (t <= points[0].t) return points[0].h;
  if (t >= points[points.length - 1].t) return points[points.length - 1].h;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    if (t >= a.t && t <= b.t) {
      const frac = (t - a.t) / (b.t - a.t);
      return a.h + (b.h - a.h) * frac;
    }
  }
  return points[points.length - 1].h;
}

function buildSkyStops(sunEvents, windowStart, windowEnd) {
  const EDGE = 0.025;
  let isDay = true;
  let determined = false;
  for (const e of sunEvents) {
    if (e.time.getTime() <= windowStart) {
      isDay = e.kind === "sunrise";
      determined = true;
    }
  }
  if (!determined && sunEvents.length) {
    // No event at/before the window start in our data - infer the state
    // right before the first event we do have from its opposite.
    isDay = sunEvents[0].kind === "sunset";
  }
  const stops = [];
  const push = (frac, day) => {
    stops.push({ offset: clamp(frac, 0, 1), color: day ? DAY_SKY : NIGHT_SKY });
  };
  push(0, isDay);
  for (const e of sunEvents) {
    const frac = (e.time.getTime() - windowStart) / (windowEnd - windowStart);
    if (frac <= 0 || frac >= 1) continue;
    const nowDay = e.kind === "sunrise";
    push(frac - EDGE, !nowDay);
    push(frac + EDGE, nowDay);
    isDay = nowDay;
  }
  push(1, isDay);
  return stops;
}

function formatTime(date, hass) {
  try {
    return new Intl.DateTimeFormat(hass?.locale?.language, {
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  } catch (err) {
    return date.toISOString().slice(11, 16);
  }
}

class TidesCard extends HTMLElement {
  static async getConfigElement() {
    return document.createElement("tides-card-editor");
  }

  static getStubConfig(hass) {
    const entityId = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && "next_high" in hass.states[id].attributes
    );
    return { entity: entityId || "", hours_to_show: 24 };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please select a tide sensor entity");
    }
    this._config = {
      show_name: true,
      hours_to_show: 24,
      ...config,
    };
    this._built = false;
  }

  getCardSize() {
    return 4;
  }

  set hass(hass) {
    this._hass = hass;
    const stateObj = hass.states[this._config.entity];
    if (!stateObj) {
      this._renderMissing();
      return;
    }
    if (stateObj === this._lastStateObj) return;
    this._lastStateObj = stateObj;
    this._renderCard(stateObj);
  }

  _shadow() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    return this.shadowRoot;
  }

  _renderMissing() {
    const root = this._shadow();
    root.innerHTML = `<ha-card><div style="padding:16px;">Entity not found: ${this._config.entity}</div></ha-card>`;
  }

  _renderCard(stateObj) {
    const attrs = stateObj.attributes;
    const amplitude = attrs.tidal_range_m || 1.5;
    const rawCurve = Array.isArray(attrs.curve) ? attrs.curve : [];
    const sunEvents = Array.isArray(attrs.sun_events)
      ? attrs.sun_events.map((e) => ({ kind: e.kind, time: new Date(e.time) }))
      : [];

    const now = Date.now();
    const totalMs = this._config.hours_to_show * 3600 * 1000;
    const backMs = totalMs * 0.15;
    const windowStart = now - backMs;
    const windowEnd = windowStart + totalMs;

    const points = rawCurve
      .map(([iso, h]) => {
        const t = new Date(iso).getTime();
        return { t, h, x: mapX(t, windowStart, windowEnd), y: mapY(h, amplitude) };
      })
      .filter((p) => p.t >= windowStart - 3600 * 1000 && p.t <= windowEnd + 3600 * 1000)
      .sort((a, b) => a.t - b.t);

    const currentHeight = interpolateHeight(
      rawCurve.map(([iso, h]) => ({ t: new Date(iso).getTime(), h })),
      now
    );
    const state = stateObj.state;
    const trendUp = state === "rising";

    const wavePath = smoothPath(points);
    const areaPath =
      points.length > 1
        ? `${wavePath} L ${points[points.length - 1].x.toFixed(2)} ${PLOT_BOTTOM} L ${points[0].x.toFixed(2)} ${PLOT_BOTTOM} Z`
        : "";

    const extrema = findLocalExtrema(points).filter(
      (e) => e.point.t >= windowStart && e.point.t <= windowEnd
    );

    const skyStops = buildSkyStops(sunEvents, windowStart, windowEnd);

    const sunMarkers = sunEvents
      .filter((e) => e.time.getTime() >= windowStart && e.time.getTime() <= windowEnd)
      .map((e) => {
        const t = e.time.getTime();
        const h = interpolateHeight(
          rawCurve.map(([iso, hh]) => ({ t: new Date(iso).getTime(), h: hh })),
          t
        );
        return { x: mapX(t, windowStart, windowEnd), y: mapY(h, amplitude) };
      });

    const axisTicks = [];
    const tickCount = 4;
    for (let i = 0; i <= tickCount; i++) {
      const t = windowStart + (totalMs * i) / tickCount;
      axisTicks.push({ x: mapX(t, windowStart, windowEnd), label: formatTime(new Date(t), this._hass) });
    }

    const nowX = mapX(now, windowStart, windowEnd);
    const nowY = mapY(currentHeight, amplitude);

    const title = this._config.title || stateObj.attributes.friendly_name || "";

    const root = this._shadow();
    root.innerHTML = `
      <style>${this._css()}</style>
      <ha-card>
        <div class="panel">
          <svg viewBox="0 0 ${WIDTH} ${HEIGHT}" preserveAspectRatio="xMidYMid meet">
            <defs>
              <linearGradient id="sky" x1="0" y1="0" x2="1" y2="0">
                ${skyStops.map((s) => `<stop offset="${s.offset}" stop-color="${s.color}" />`).join("")}
              </linearGradient>
              <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="${WATER_TOP}" />
                <stop offset="1" stop-color="${WATER_BOTTOM}" />
              </linearGradient>
            </defs>
            <rect x="0" y="0" width="${WIDTH}" height="${HEIGHT}" fill="url(#sky)" />
            ${areaPath ? `<path d="${areaPath}" fill="url(#sea)" fill-opacity="0.92" />` : ""}
            ${wavePath ? `<path class="wave-line" d="${wavePath}" fill="none" />` : ""}
            ${sunMarkers.map((m) => `<circle class="sun-dot" cx="${m.x.toFixed(2)}" cy="${m.y.toFixed(2)}" r="5" />`).join("")}
            ${extrema
              .map((e) => {
                const above = e.kind === "high";
                const labelY = above ? e.point.y - 14 : e.point.y + 22;
                const stemY2 = above ? e.point.y - 8 : e.point.y + 8;
                return `
                  <line class="tick-stem" x1="${e.point.x.toFixed(2)}" y1="${e.point.y.toFixed(2)}" x2="${e.point.x.toFixed(2)}" y2="${stemY2.toFixed(2)}" />
                  <circle class="extreme-dot" cx="${e.point.x.toFixed(2)}" cy="${e.point.y.toFixed(2)}" r="3" />
                  <text class="halo-text label-text" x="${e.point.x.toFixed(2)}" y="${labelY.toFixed(2)}" text-anchor="middle">${formatTime(new Date(e.point.t), this._hass)}</text>
                `;
              })
              .join("")}
            ${axisTicks
              .map(
                (tick) => `
                  <line class="axis-tick" x1="${tick.x.toFixed(2)}" y1="${PLOT_BOTTOM + 4}" x2="${tick.x.toFixed(2)}" y2="${PLOT_BOTTOM + 9}" />
                  <text class="halo-text axis-text" x="${tick.x.toFixed(2)}" y="${HEIGHT - 8}" text-anchor="middle">${tick.label}</text>
                `
              )
              .join("")}
            <circle class="now-ring" cx="${nowX.toFixed(2)}" cy="${nowY.toFixed(2)}" r="4" />
            <circle class="now-dot" cx="${nowX.toFixed(2)}" cy="${nowY.toFixed(2)}" r="4" />
          </svg>
          <div class="overlay">
            ${this._config.show_name && title ? `<div class="caption">${title}</div>` : ""}
            <div class="reading">
              <span class="height">${currentHeight.toFixed(1)}<small>m</small></span>
              <svg class="trend ${trendUp ? "up" : "down"}" viewBox="0 0 24 24"><path d="M6 15l6-6 6 6" /></svg>
            </div>
          </div>
        </div>
      </ha-card>
    `;
  }

  _css() {
    return `
      ha-card { overflow: hidden; padding: 0; }
      .panel {
        position: relative;
        aspect-ratio: ${WIDTH} / ${HEIGHT};
        width: 100%;
      }
      svg { display: block; width: 100%; height: 100%; }
      .wave-line {
        stroke: ${WAVE_LINE};
        stroke-width: 2.5;
        stroke-linecap: round;
        stroke-linejoin: round;
        filter: drop-shadow(0 0 3px rgba(189, 238, 255, 0.55));
      }
      .sun-dot {
        fill: ${SUN_COLOR};
        filter: drop-shadow(0 0 4px rgba(247, 185, 85, 0.85));
      }
      .extreme-dot { fill: #eef6fa; }
      .tick-stem { stroke: rgba(238, 246, 250, 0.45); stroke-width: 1.5; }
      .axis-tick { stroke: rgba(238, 246, 250, 0.35); stroke-width: 1; }
      .halo-text {
        font-family: var(--paper-font-common-base_-_font-family, inherit);
        fill: #eef6fa;
        paint-order: stroke fill;
        stroke: rgba(4, 10, 26, 0.55);
        stroke-width: 3;
        stroke-linejoin: round;
      }
      .label-text { font-size: 16px; font-variant-numeric: tabular-nums; }
      .axis-text { font-size: 12px; opacity: 0.8; font-variant-numeric: tabular-nums; }
      .now-dot { fill: ${NOW_COLOR}; }
      .now-ring {
        fill: none;
        stroke: ${NOW_COLOR};
        stroke-width: 2;
        transform-origin: center;
        transform-box: fill-box;
        animation: tide-pulse 2.6s ease-out infinite;
      }
      @keyframes tide-pulse {
        0% { r: 4; stroke-opacity: 0.7; }
        100% { r: 16; stroke-opacity: 0; }
      }
      @media (prefers-reduced-motion: reduce) {
        .now-ring { animation: none; stroke-opacity: 0.35; }
      }
      .overlay {
        position: absolute;
        top: 10px;
        left: 14px;
        color: #eef6fa;
        text-shadow: 0 1px 6px rgba(0, 0, 0, 0.55), 0 0 2px rgba(0, 0, 0, 0.5);
        pointer-events: none;
      }
      .caption {
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        opacity: 0.85;
        margin-bottom: 2px;
      }
      .reading { display: flex; align-items: baseline; gap: 6px; }
      .height { font-size: 28px; font-weight: 300; font-variant-numeric: tabular-nums; line-height: 1; }
      .height small { font-size: 14px; font-weight: 400; margin-left: 1px; }
      .trend { width: 16px; height: 16px; transform: translateY(-2px); }
      .trend path { fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
      .trend.up path { stroke: ${RISING_COLOR}; }
      .trend.down { transform: translateY(1px) rotate(180deg); }
      .trend.down path { stroke: ${FALLING_COLOR}; }
    `;
  }
}

const SCHEMA = [
  { name: "entity", selector: { entity: { domain: "sensor" } } },
  { name: "title", selector: { text: {} } },
  {
    name: "hours_to_show",
    selector: { number: { min: 12, max: 48, step: 1, mode: "slider" } },
  },
  { name: "show_name", selector: { boolean: {} } },
];

const LABELS = {
  entity: "Tide sensor",
  title: "Title (optional)",
  hours_to_show: "Hours to show",
  show_name: "Show name on card",
};

class TidesCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { show_name: true, hours_to_show: 24, ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        this._config = ev.detail.value;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config } }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = SCHEMA;
    this._form.computeLabel = (s) => LABELS[s.name] || s.name;
  }
}

customElements.define("tides-card", TidesCard);
customElements.define("tides-card-editor", TidesCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "tides-card",
  name: "Tides",
  description: "A minimal wave showing the current tide, next high/low, and sunrise/sunset.",
  preview: true,
});
