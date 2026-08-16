// Tides card - a minimal wave showing current tide level, the next
// high/low, and sunrise/sunset, all read off one timeline. Transparent
// background - it sits directly on the card's (themed) surface.

const WIDTH = 600;
const HEIGHT = 200;
const PAD_X = 18;
const PAD_TOP = 54;
const PAD_BOTTOM = 30;
const PLOT_TOP = PAD_TOP;
const PLOT_BOTTOM = HEIGHT - PAD_BOTTOM;
const AMPLITUDE_MARGIN = 1.25;

const SUNRISE_COLOR = "#f2b94f";
const SUNSET_COLOR = "#7c93e8";
const RISING_COLOR = "#2e9e64";
const FALLING_COLOR = "#d9534f";

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
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
    if (cur >= prev && cur >= next) {
      events.push({ kind: "high", point: points[i] });
    } else if (cur <= prev && cur <= next) {
      events.push({ kind: "low", point: points[i] });
    }
  }
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
    root.innerHTML = `<ha-card><div style="padding:16px;">Entity not found: ${escapeHtml(this._config.entity)}</div></ha-card>`;
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

    const flatCurve = rawCurve.map(([iso, h]) => ({ t: new Date(iso).getTime(), h }));

    const points = rawCurve
      .map(([iso, h]) => {
        const t = new Date(iso).getTime();
        return { t, h, x: mapX(t, windowStart, windowEnd), y: mapY(h, amplitude) };
      })
      .filter((p) => p.t >= windowStart - 3600 * 1000 && p.t <= windowEnd + 3600 * 1000)
      .sort((a, b) => a.t - b.t);

    const currentHeight = interpolateHeight(flatCurve, now);
    const state = stateObj.state;
    const trendUp = state === "rising";

    const wavePath = smoothPath(points);

    const extrema = findLocalExtrema(points).filter(
      (e) => e.point.t >= windowStart && e.point.t <= windowEnd
    );

    const sunMarkers = sunEvents
      .filter((e) => e.time.getTime() >= windowStart && e.time.getTime() <= windowEnd)
      .map((e) => {
        const t = e.time.getTime();
        const h = interpolateHeight(flatCurve, t);
        return { x: mapX(t, windowStart, windowEnd), y: mapY(h, amplitude), kind: e.kind };
      });

    const axisTicks = [];
    const tickCount = 4;
    for (let i = 0; i <= tickCount; i++) {
      const t = windowStart + (totalMs * i) / tickCount;
      axisTicks.push({ x: mapX(t, windowStart, windowEnd), label: formatTime(new Date(t), this._hass) });
    }

    const nowX = mapX(now, windowStart, windowEnd);
    const nowY = mapY(currentHeight, amplitude);

    const nextEvent = [attrs.next_high, attrs.next_low]
      .filter(Boolean)
      .sort((a, b) => new Date(a.time) - new Date(b.time))[0];

    const title = this._config.title || stateObj.attributes.friendly_name || "";
    const showHeader = this._config.show_name && title;

    const root = this._shadow();
    root.innerHTML = `
      <style>${this._css()}</style>
      <ha-card ${showHeader ? `header="${escapeHtml(title)}"` : ""}>
        <div class="panel">
          <svg viewBox="0 0 ${WIDTH} ${HEIGHT}" preserveAspectRatio="xMidYMid meet">
            ${wavePath ? `<path class="wave-line" d="${wavePath}" fill="none" />` : ""}
            ${extrema
              .map((e) => `<circle class="extreme-dot" cx="${e.point.x.toFixed(2)}" cy="${e.point.y.toFixed(2)}" r="3.5" />`)
              .join("")}
            ${sunMarkers
              .map((m) => `<circle class="sun-dot ${m.kind === "sunrise" ? "rise" : "set"}" cx="${m.x.toFixed(2)}" cy="${m.y.toFixed(2)}" r="5" />`)
              .join("")}
            ${axisTicks
              .map(
                (tick) => `
                  <line class="axis-tick" x1="${tick.x.toFixed(2)}" y1="${PLOT_BOTTOM + 4}" x2="${tick.x.toFixed(2)}" y2="${PLOT_BOTTOM + 9}" />
                  <text class="axis-text" x="${tick.x.toFixed(2)}" y="${HEIGHT - 8}" text-anchor="middle">${tick.label}</text>
                `
              )
              .join("")}
            <circle class="now-ring" cx="${nowX.toFixed(2)}" cy="${nowY.toFixed(2)}" r="8" />
            <circle class="now-pulse" cx="${nowX.toFixed(2)}" cy="${nowY.toFixed(2)}" r="8" />
            <circle class="now-dot" cx="${nowX.toFixed(2)}" cy="${nowY.toFixed(2)}" r="3.5" />
          </svg>
          <div class="overlay">
            <div class="now">
              <div class="caption">Now</div>
              <div class="reading">
                <span class="height">${currentHeight.toFixed(1)}<small>m</small></span>
                <svg class="trend ${trendUp ? "up" : "down"}" viewBox="0 0 24 24"><path d="M6 15l6-6 6 6" /></svg>
              </div>
            </div>
            ${
              nextEvent
                ? `
                  <div class="next">
                    <div class="caption">${escapeHtml(nextEvent.kind)}</div>
                    <div class="reading">${formatTime(new Date(nextEvent.time), this._hass)}</div>
                  </div>
                `
                : ""
            }
          </div>
        </div>
      </ha-card>
    `;
  }

  _css() {
    return `
      ha-card { background: transparent; box-shadow: none; overflow: hidden; }
      .panel {
        position: relative;
        aspect-ratio: ${WIDTH} / ${HEIGHT};
        width: 100%;
      }
      svg { display: block; width: 100%; height: 100%; }
      .wave-line {
        stroke: var(--tides-line-color, #2f9cc4);
        stroke-width: 2.5;
        stroke-linecap: round;
        stroke-linejoin: round;
      }
      .extreme-dot { fill: var(--tides-line-color, #2f9cc4); opacity: 0.6; }
      .sun-dot.rise { fill: ${SUNRISE_COLOR}; }
      .sun-dot.set { fill: ${SUNSET_COLOR}; }
      .axis-tick { stroke: var(--secondary-text-color); stroke-opacity: 0.3; stroke-width: 1; }
      .axis-text {
        fill: var(--secondary-text-color);
        opacity: 0.75;
        font-family: var(--paper-font-common-base_-_font-family, inherit);
        font-size: 12px;
        font-variant-numeric: tabular-nums;
      }
      .now-dot { fill: var(--primary-color, #03a9f4); }
      .now-ring {
        fill: none;
        stroke: var(--primary-color, #03a9f4);
        stroke-width: 3;
      }
      .now-pulse {
        fill: none;
        stroke: var(--primary-color, #03a9f4);
        stroke-width: 2;
        transform-origin: center;
        transform-box: fill-box;
        animation: tide-pulse 2.6s ease-out infinite;
      }
      @keyframes tide-pulse {
        0% { r: 8; stroke-opacity: 0.5; }
        100% { r: 20; stroke-opacity: 0; }
      }
      @media (prefers-reduced-motion: reduce) {
        .now-pulse { animation: none; opacity: 0; }
      }
      .overlay {
        position: absolute;
        top: 10px;
        left: 14px;
        right: 14px;
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        pointer-events: none;
        font-family: var(--paper-font-common-base_-_font-family, inherit);
      }
      .next { text-align: right; }
      .caption {
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--secondary-text-color);
        margin-bottom: 2px;
      }
      .reading { display: flex; align-items: baseline; gap: 6px; }
      .next .reading {
        font-size: 22px;
        font-weight: 400;
        color: var(--primary-text-color);
        font-variant-numeric: tabular-nums;
      }
      .height {
        font-size: 28px;
        font-weight: 300;
        color: var(--primary-text-color);
        font-variant-numeric: tabular-nums;
        line-height: 1;
      }
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
