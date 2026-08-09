const DANGER_LABELS = {
  1: "Low",
  2: "Moderate",
  3: "Considerable",
  4: "High",
  5: "Extreme",
};
const DANGER_CLASSES = {
  1: "danger-low",
  2: "danger-moderate",
  3: "danger-considerable",
  4: "danger-high",
  5: "danger-extreme",
};

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function decodeDegrees(str) {
  // Hoodoo's source HTML omits the trailing ";" on this entity, so match it
  // with or without one.
  return typeof str === "string" ? str.replace(/&#176;?/g, "°") : str;
}

function statRow(label, value, valueClass) {
  const row = el("div", "stat-row");
  row.appendChild(el("span", "label", label));
  row.appendChild(el("span", `value${valueClass ? " " + valueClass : ""}`, value));
  return row;
}

function formatSnowDelta(value) {
  if (value === null || value === undefined) return { text: "—", cls: "" };
  if (value === 0) return { text: '0.0"', cls: "" };
  return { text: `${value > 0 ? "+" : ""}${value}"`, cls: value > 0 ? "positive" : "negative" };
}

const COMPASS_POINTS = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
];

function degToCompass(deg) {
  if (deg === null || deg === undefined) return "—";
  return COMPASS_POINTS[Math.round(deg / 22.5) % 16];
}

// Compass dial with an arrow pointing toward where the wind is blowing TO
// (downwind - the reported wind_direction_deg is the standard meteorological
// "from" bearing, so this rotates it 180deg). 0deg/N is up, clockwise.
function windRoseSvg(directionDeg, { size = 180, showLabels = true, background = "none" } = {}) {
  const cx = 100, cy = 100, r = 78;
  let arrow = "";
  if (directionDeg !== null && directionDeg !== undefined) {
    const rad = ((directionDeg + 180) * Math.PI) / 180;
    const dx = Math.sin(rad), dy = -Math.cos(rad);
    const px = Math.cos(rad), py = Math.sin(rad); // perpendicular to (dx, dy)

    const tailX = cx - r * 0.5 * dx, tailY = cy - r * 0.5 * dy;
    const tipX = cx + r * dx, tipY = cy + r * dy;

    const headLen = 22, headWidth = 11;
    const baseX = tipX - headLen * dx, baseY = tipY - headLen * dy;
    const leftX = baseX + headWidth * px, leftY = baseY + headWidth * py;
    const rightX = baseX - headWidth * px, rightY = baseY - headWidth * py;

    arrow = `
      <line x1="${tailX.toFixed(1)}" y1="${tailY.toFixed(1)}" x2="${baseX.toFixed(1)}" y2="${baseY.toFixed(1)}"
        stroke="var(--accent)" stroke-width="5" stroke-linecap="round" />
      <polygon points="${tipX.toFixed(1)},${tipY.toFixed(1)} ${leftX.toFixed(1)},${leftY.toFixed(1)} ${rightX.toFixed(1)},${rightY.toFixed(1)}"
        fill="var(--accent)" />`;
  }
  const labels = showLabels ? `
      <text x="100" y="20" text-anchor="middle" fill="var(--text-dim)" font-size="14">N</text>
      <text x="180" y="105" text-anchor="middle" fill="var(--text-dim)" font-size="14">E</text>
      <text x="100" y="190" text-anchor="middle" fill="var(--text-dim)" font-size="14">S</text>
      <text x="20" y="105" text-anchor="middle" fill="var(--text-dim)" font-size="14">W</text>` : "";
  return `
    <svg viewBox="0 0 200 200" width="${size}" height="${size}">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="${background}" stroke="var(--panel-border)" stroke-width="2" />
      <circle cx="${cx}" cy="${cy}" r="4" fill="var(--text-dim)" />
      ${labels}
      ${arrow}
    </svg>`;
}

// Bare directional arrow (no compass ring) - same downwind convention as
// windRoseSvg, sized for tight spaces like map callout cards.
function directionArrowSvg(directionDeg, size = 14) {
  if (directionDeg === null || directionDeg === undefined) return "";
  const rot = (directionDeg + 180) % 360;
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" style="transform:rotate(${rot}deg); flex: none;">
    <path d="M12 3 L12 21 M12 3 L6.5 9.5 M12 3 L17.5 9.5"
      stroke="var(--accent)" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round" />
  </svg>`;
}

// Derives a plain-language conditions summary purely from live data already
// in conditions.json - nothing here is stored or cached, so it's naturally
// "fresh" every time the page loads, and genuinely fresh every ~24 hours as
// long as conditions.json itself is rebuilt at least that often. The verdict
// sentence is threshold-based on real temp/precip, not a calendar check, so
// it reads correctly in any season rather than hardcoding "summer".
function buildBachelorSummary(data) {
  const currentTemp = data?.mtbachelor?.weather?.current?.temperature;
  const wr = data?.wind_roses?.["Mt Bachelor"];
  const hourly = data?.bachelor_timeseries?.hourly;
  if (currentTemp === undefined || !wr || !hourly) return null;

  const historical = hourly.filter((p) => p.period === "historical");
  const forecast = hourly.filter((p) => p.period === "forecast");

  const histTemps = historical.map((p) => p.temp_f).filter((v) => v !== null && v !== undefined);
  let recentTempMin = histTemps.length ? Math.min(...histTemps) : null;
  let recentTempMax = histTemps.length ? Math.max(...histTemps) : null;

  let recentWindMax = null, recentWindMaxDir = null;
  for (const p of historical) {
    if (p.wind_speed_mph !== null && p.wind_speed_mph !== undefined &&
        (recentWindMax === null || p.wind_speed_mph > recentWindMax)) {
      recentWindMax = p.wind_speed_mph;
      recentWindMaxDir = p.wind_direction_deg;
    }
  }

  const nowMs = Date.now();
  const forecast48 = forecast.filter((p) => {
    const t = new Date(p.time).getTime();
    return t >= nowMs && t <= nowMs + 48 * 3600 * 1000;
  });
  const fcTemps = forecast48.map((p) => p.temp_f).filter((v) => v !== null && v !== undefined);
  const fcTempMin = fcTemps.length ? Math.min(...fcTemps) : null;
  const fcTempMax = fcTemps.length ? Math.max(...fcTemps) : null;
  const fcPrecipTotal = forecast48.reduce((sum, p) => sum + (p.precip_in || 0), 0);

  // Sentence 1: right now.
  const s1 = `Current conditions at Mt. Bachelor are ${Math.round(currentTemp)}°F, with wind blowing ` +
    `from the ${degToCompass(wr.wind_direction_deg)} at ${wr.wind_speed_mph ?? "—"} mph.`;

  // Sentence 2: last 24h of real sensor data, plus the resort's own real
  // 48hr snowfall total (kept as a separate real window, not stretched to
  // cover the 24hr temp/wind figures too).
  const precip48 = wr.snowfall_48h_in;
  const precipDesc = precip48 === null || precip48 === undefined
    ? "no snowfall data available for the last 48 hours"
    : precip48 === 0
      ? "no precipitation over the last 48 hours"
      : precip48 < 0.3
        ? `light precipitation over the last 48 hours (${precip48}")`
        : `heavy precipitation over the last 48 hours (${precip48}")`;
  const s2 = (recentTempMin !== null && recentWindMax !== null)
    ? `The last 24 hours have seen wind from the ${degToCompass(recentWindMaxDir)} up to ${Math.round(recentWindMax)} mph, ` +
      `temps between ${Math.round(recentTempMin)}° and ${Math.round(recentTempMax)}°, and ${precipDesc}.`
    : null;

  // Sentence 3: next 48h forecast.
  const s3 = (fcTempMin !== null)
    ? `The next 48 hours are forecast to bring temps between ${Math.round(fcTempMin)}° and ${Math.round(fcTempMax)}°, ` +
      `with ${fcPrecipTotal < 0.01 ? "no precipitation expected" : `${fcPrecipTotal.toFixed(2)}" of total precipitation expected`}.`
    : null;

  // Sentence 4: verdict, purely threshold-driven off real cold/wet data
  // above - reads correctly whether it's a January storm or a dry August.
  const coldEnough = [recentTempMin, fcTempMin].some((t) => t !== null && t <= 32);
  const wet = fcPrecipTotal > 0.05 || (precip48 !== null && precip48 > 0.05);
  let s4;
  if (coldEnough && wet) {
    s4 = "Overall, cold temps and incoming precipitation add up to real skiing potential.";
  } else if (wet) {
    s4 = "Overall, precipitation is around but with temps staying above freezing, expect rain - not snow.";
  } else if (coldEnough) {
    s4 = "Overall, temps are cold enough for snow, but there's no precipitation to work with.";
  } else {
    s4 = "Overall, temps are running well above freezing with no precipitation in sight - firmly summer conditions, no skiing to be done.";
  }

  return [s1, s2, s3, s4].filter(Boolean).join(" ");
}

function renderSummarySection(container, data) {
  const section = el("section");
  section.appendChild(el("h2", null, "Conditions Summary"));
  const summary = buildBachelorSummary(data);
  if (!summary) {
    section.appendChild(el("p", "error-text", "Not enough data to summarize conditions right now."));
  } else {
    section.appendChild(el("p", "conditions-summary", summary));
  }
  container.appendChild(section);
}

function renderWindRoseSection(container, windRoseData) {
  const section = el("section");
  section.appendChild(el("h2", null, "Current Conditions"));
  if (windRoseData?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${windRoseData.error}`));
    container.appendChild(section);
    return;
  }

  const grid = el("div", "wind-rose-grid");
  for (const [name, info] of Object.entries(windRoseData || {})) {
    const card = el("div", "card wind-rose-card");
    card.appendChild(el("h3", null, name));
    card.appendChild(el("div", "sub", `${info.elevation_ft.toLocaleString()} ft`));

    const dial = document.createElement("div");
    dial.innerHTML = windRoseSvg(info.wind_direction_deg);
    card.appendChild(dial);

    card.appendChild(el("div", "big-temp",
      `${info.temp_f !== null && info.temp_f !== undefined ? info.temp_f + "°F" : "—"}`));
    card.appendChild(statRow("Wind", `${info.wind_speed_mph ?? "—"} mph ${degToCompass(info.wind_direction_deg)}`));
    card.appendChild(statRow("Snow level", info.snow_level_ft !== null ? `${info.snow_level_ft.toLocaleString()} ft` : "—"));
    card.appendChild(statRow("Precip. chance today", `${info.precip_chance_today ?? 0}%`));

    const fmtSnowfall = (v) => (v === null || v === undefined ? "—" : `${v}"`);
    card.appendChild(statRow("Snowfall, 12 hr", fmtSnowfall(info.snowfall_12h_in)));
    card.appendChild(statRow("Snowfall, 24 hr", fmtSnowfall(info.snowfall_24h_in)));
    card.appendChild(statRow("Snowfall, 48 hr", fmtSnowfall(info.snowfall_48h_in)));

    grid.appendChild(card);
  }
  section.appendChild(grid);
  container.appendChild(section);
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function drawWindArrow(ctx, cx, cy, directionDeg, size, color) {
  // Points downwind - same convention as the wind-rose dials above.
  const rad = ((directionDeg + 180) * Math.PI) / 180;
  const dx = Math.sin(rad), dy = -Math.cos(rad);
  const px = Math.cos(rad), py = Math.sin(rad);
  const tipX = cx + dx * size, tipY = cy + dy * size;
  const tailX = cx - dx * size, tailY = cy - dy * size;
  const headLen = size * 0.55;
  const baseX = tipX - dx * headLen, baseY = tipY - dy * headLen;

  ctx.strokeStyle = color;
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  ctx.moveTo(tailX, tailY);
  ctx.lineTo(baseX, baseY);
  ctx.stroke();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(tipX, tipY);
  ctx.lineTo(baseX + px * headLen * 0.45, baseY + py * headLen * 0.45);
  ctx.lineTo(baseX - px * headLen * 0.45, baseY - py * headLen * 0.45);
  ctx.closePath();
  ctx.fill();
}

function drawYAxisTicks(ctx, top, height, marginLeft, minVal, maxVal, formatFn, textDimColor, gridColor, plotWidth, ticks = 4) {
  ctx.textAlign = "right";
  for (let i = 0; i <= ticks; i++) {
    const frac = i / ticks;
    const val = minVal + (maxVal - minVal) * frac;
    const y = top + height - frac * height;
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(marginLeft, y);
    ctx.lineTo(marginLeft + plotWidth, y);
    ctx.stroke();
    ctx.fillStyle = textDimColor;
    ctx.fillText(formatFn(val), marginLeft - 6, y + 3);
  }
}

function drawTimeseriesChart(canvas, points, historicalPrecipSnapshots) {
  const colors = {
    border: "#2a3850",
    text: "#e7edf5",
    textDim: "#93a3ba",
    temp: "#ff9f5e",
    wind: "#5eb1ff",
    precip: "#7fd0ff",
    now: "#ff5e5e",
    gridLine: "rgba(255,255,255,0.06)",
  };

  const sorted = [...points].sort((a, b) => new Date(a.time) - new Date(b.time));
  const times = sorted.map((p) => new Date(p.time).getTime());
  const minT = Math.min(...times);
  const maxT = Math.max(...times);
  const nowMs = Date.now();

  const marginLeft = 54, marginRight = 14, marginTop = 4, marginBottom = 28;
  const panelGap = 20;
  const tempH = 130, windH = 110, precipH = 80;
  const windArrowRowH = 20;

  const cssWidth = Math.max(canvas.parentElement.clientWidth || 900, 320);
  const cssHeight = marginTop + tempH + panelGap + windH + panelGap + precipH + marginBottom;

  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = "100%";
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.font = "11px ui-sans-serif, system-ui, sans-serif";

  const plotWidth = cssWidth - marginLeft - marginRight;
  const xForTime = (t) => marginLeft + ((t - minT) / (maxT - minT)) * plotWidth;

  const tempTop = marginTop;
  const windTop = tempTop + tempH + panelGap;
  const precipTop = windTop + windH + panelGap;
  const bottom = precipTop + precipH;

  function panelFrame(top, height, label) {
    ctx.strokeStyle = colors.border;
    ctx.lineWidth = 1;
    ctx.strokeRect(marginLeft, top, plotWidth, height);
    ctx.fillStyle = colors.textDim;
    ctx.textAlign = "left";
    ctx.fillText(label, marginLeft, top - 6);
  }
  panelFrame(tempTop, tempH, "Temperature (°F)");
  panelFrame(windTop, windH, "Wind Speed (mph) & Direction");
  panelFrame(precipTop, precipH, "Precipitation (in)");

  // ---- X-axis: hours relative to "now" ----
  ctx.textAlign = "center";
  for (const h of [-24, 24, 48, 72]) {
    const t = nowMs + h * 3600 * 1000;
    if (t < minT || t > maxT) continue;
    const x = xForTime(t);
    ctx.strokeStyle = colors.gridLine;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, tempTop);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.fillStyle = colors.textDim;
    ctx.fillText(String(h), x, bottom + 16);
  }

  // ---- Temperature line ----
  const temps = sorted.map((p) => p.temp_f).filter((v) => v !== null && v !== undefined);
  if (temps.length > 0) {
    const tMin = Math.min(...temps) - 3;
    const tMax = Math.max(...temps) + 3;
    const yForTemp = (v) => tempTop + tempH - ((v - tMin) / (tMax - tMin)) * tempH;

    drawYAxisTicks(ctx, tempTop, tempH, marginLeft, tMin, tMax, (v) => `${Math.round(v)}°`, colors.textDim, colors.gridLine, plotWidth);

    ctx.strokeStyle = colors.temp;
    ctx.lineWidth = 2;
    ctx.beginPath();
    let started = false;
    for (const p of sorted) {
      if (p.temp_f === null || p.temp_f === undefined) { started = false; continue; }
      const x = xForTime(new Date(p.time).getTime());
      const y = yForTemp(p.temp_f);
      if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
    }
    ctx.stroke();
  }

  // ---- Wind speed bars (bottom of panel) + direction arrows (top row) ----
  const barSlot = plotWidth / sorted.length;
  const barWidth = Math.max(1, barSlot * 0.6);
  const winds = sorted.map((p) => p.wind_speed_mph).filter((v) => v !== null && v !== undefined);
  const wMax = Math.max(4, ...winds) * 1.15;
  const windBarAreaH = windH - windArrowRowH;

  drawYAxisTicks(ctx, windTop + windArrowRowH, windBarAreaH, marginLeft, 0, wMax, (v) => Math.round(v), colors.textDim, colors.gridLine, plotWidth);

  ctx.fillStyle = colors.wind;
  for (const p of sorted) {
    if (p.wind_speed_mph === null || p.wind_speed_mph === undefined) continue;
    const x = xForTime(new Date(p.time).getTime());
    const barH = (p.wind_speed_mph / wMax) * windBarAreaH;
    ctx.fillRect(x - barWidth / 2, windTop + windH - barH, barWidth, barH);
  }

  // one arrow every 6 hours - one per hour would overlap into an unreadable smear
  for (const p of sorted) {
    const t = new Date(p.time);
    if (t.getUTCHours() % 6 !== 0) continue;
    if (p.wind_direction_deg === null || p.wind_direction_deg === undefined) continue;
    const x = xForTime(t.getTime());
    drawWindArrow(ctx, x, windTop + windArrowRowH / 2, p.wind_direction_deg, 8, colors.text);
  }

  // ---- Precipitation bars ----
  // Forecast side is real hourly NWS data. Historical side has no hourly
  // breakdown available (Mt Bachelor's site only exposes a rolling 24hr
  // total) - each historical bar is one real logged snapshot of that total,
  // drawn at the time it was actually recorded, not a fabricated split.
  const forecastPrecips = sorted.filter((p) => p.period === "forecast").map((p) => p.precip_in).filter((v) => v !== null && v !== undefined);
  const historicalPrecips = (historicalPrecipSnapshots || []).map((s) => s.precip_in).filter((v) => v !== null && v !== undefined);
  const pMax = Math.max(0.1, ...forecastPrecips, ...historicalPrecips) * 1.15;

  drawYAxisTicks(ctx, precipTop, precipH, marginLeft, 0, pMax, (v) => `${v.toFixed(2)}"`, colors.textDim, colors.gridLine, plotWidth);

  ctx.fillStyle = colors.precip;
  for (const p of sorted) {
    if (p.period !== "forecast" || p.precip_in === null || p.precip_in === undefined) continue;
    const x = xForTime(new Date(p.time).getTime());
    const barH = (p.precip_in / pMax) * precipH;
    ctx.fillRect(x - barWidth / 2, precipTop + precipH - barH, barWidth, barH);
  }
  const snapBarWidth = Math.max(2, barWidth);
  for (const snap of historicalPrecipSnapshots || []) {
    if (snap.precip_in === null || snap.precip_in === undefined) continue;
    const t = new Date(snap.time).getTime();
    if (t < minT || t > maxT) continue;
    const x = xForTime(t);
    const barH = (snap.precip_in / pMax) * precipH;
    ctx.fillRect(x - snapBarWidth / 2, precipTop + precipH - barH, snapBarWidth, barH);
  }

  // ---- "Now" marker, drawn last so it's on top ----
  if (nowMs >= minT && nowMs <= maxT) {
    const nowX = xForTime(nowMs);
    ctx.strokeStyle = colors.now;
    ctx.setLineDash([4, 3]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(nowX, tempTop);
    ctx.lineTo(nowX, bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = colors.now;
    ctx.textAlign = "center";
    ctx.fillText("0", nowX, bottom + 16);
    ctx.fillText("Now", nowX, tempTop - 6);
  }
}

function renderBachelorTimeseries(container, data) {
  const section = el("section");
  section.appendChild(el("h2", null, "Mt. Bachelor: 3-Day History + 3-Day Forecast"));
  if (!data || data.error || !data.hourly) {
    section.appendChild(el("p", "error-text", `Failed to load: ${data?.error ?? "no data"}`));
    container.appendChild(section);
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "timeseries-wrap";
  const canvas = document.createElement("canvas");
  wrap.appendChild(canvas);
  section.appendChild(wrap);
  container.appendChild(section);

  const redraw = () => drawTimeseriesChart(canvas, data.hourly, data.historical_precip_snapshots);
  redraw();
  window.addEventListener("resize", debounce(redraw, 200));
}

function renderMapSection(container, forecastData) {
  const section = el("section");
  section.appendChild(el("h2", null, "Central Oregon Map"));
  if (forecastData?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${forecastData.error}`));
    container.appendChild(section);
    return;
  }
  if (typeof L === "undefined") {
    section.appendChild(el("p", "error-text", "Map library (Leaflet) failed to load."));
    container.appendChild(section);
    return;
  }

  // Wrapper is shorter than the map itself and clips the overflow - crops
  // the bottom third off what's visible without touching the map's actual
  // size, so fitBounds() below still computes zoom/pan against the original
  // (taller) dimensions and the view stays exactly where it already was,
  // just with the bottom sliced away instead of Leaflet re-fitting to a
  // shorter box (which would re-zoom/re-pan everything).
  const mapWrap = document.createElement("div");
  mapWrap.className = "map-crop-wrap";
  const mapDiv = document.createElement("div");
  mapDiv.id = "map";
  mapWrap.appendChild(mapDiv);
  section.appendChild(mapWrap);
  container.appendChild(section);

  // Interactive: pan/zoom enabled. Markers are real L.marker instances tied
  // to lat/lon, so Leaflet repositions the dot/leader-line/callout together
  // as one unit on every pan/zoom automatically - no extra tracking code
  // needed. resolveCardOverlaps() below only runs once at initial load, so
  // panning/zooming can re-expose the odd overlap it would have resolved at
  // the original view - a cosmetic tradeoff of a static one-time layout
  // pass, not a functional bug.
  const map = L.map(mapDiv, {
    zoomControl: true,
    dragging: true,
    scrollWheelZoom: true,
    doubleClickZoom: true,
    boxZoom: true,
    keyboard: true,
    tap: true,
  });

  L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
    maxZoom: 17,
    attribution: "Map: OpenTopoMap (CC-BY-SA) | Data: OpenStreetMap contributors, SRTM",
  }).addTo(map);

  // Leader-line callout: a dot at the true coordinate, a thin line out to a
  // detail card nudged clear of it. Seed directions get every card pointing
  // somewhere reasonable to start; resolveCardOverlaps() then measures the
  // actual rendered cards and nudges any that still collide apart, so this
  // adapts automatically instead of needing hand-tuning every time a point
  // is added or the map's auto-fit zoom changes.
  const SEED_OFFSETS = {
    "Mt Bachelor": { dx: -55, dy: 45 },
    "Tam McArthur Rim": { dx: -70, dy: 5 },
    "Hoodoo": { dx: 60, dy: -20 },
    "Tombstone Pass": { dx: -60, dy: -20 },
    "Paulina Peak": { dx: 55, dy: 45 },
    "Bend": { dx: 60, dy: 10 },
    "Willamette Pass": { dx: 0, dy: 60 },
    "Sisters": { dx: 0, dy: -55 },
    "Ochoco Meadows": { dx: 65, dy: 0 },
  };
  const DEFAULT_OFFSET = { dx: 0, dy: -55 };

  function updateCalloutPosition(marker) {
    const { dx, dy } = marker;
    marker.lineEl.style.width = `${Math.hypot(dx, dy)}px`;
    marker.lineEl.style.transform = `rotate(${Math.atan2(dy, dx) * (180 / Math.PI)}deg)`;
    marker.cardEl.style.left = `${dx}px`;
    marker.cardEl.style.top = `${dy}px`;
    marker.cardEl.style.transform = `translate(${dx >= 0 ? "0%" : "-100%"}, -50%)`;
  }

  // Iteratively push any pair of overlapping cards apart along the line
  // between their centers until nothing overlaps (or we give up after a
  // fixed number of passes, to guarantee this always terminates).
  function resolveCardOverlaps(markers) {
    for (let pass = 0; pass < 40; pass++) {
      let anyOverlap = false;
      for (let i = 0; i < markers.length; i++) {
        for (let j = i + 1; j < markers.length; j++) {
          const a = markers[i], b = markers[j];
          const ra = a.cardEl.getBoundingClientRect();
          const rb = b.cardEl.getBoundingClientRect();
          const overlapX = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
          const overlapY = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
          if (overlapX <= 0 || overlapY <= 0) continue;

          anyOverlap = true;
          let vx = (rb.left + rb.width / 2) - (ra.left + ra.width / 2);
          let vy = (rb.top + rb.height / 2) - (ra.top + ra.height / 2);
          const dist = Math.hypot(vx, vy) || 1;
          vx /= dist;
          vy /= dist;
          const push = Math.min(overlapX, overlapY) / 2 + 2;
          a.dx -= vx * push;
          a.dy -= vy * push;
          b.dx += vx * push;
          b.dy += vy * push;
          updateCalloutPosition(a);
          updateCalloutPosition(b);
        }
      }
      if (!anyOverlap) break;
    }
  }

  const points = [];
  for (const forecast of Object.values(forecastData || {})) {
    if (forecast.lat !== undefined && forecast.lon !== undefined) {
      points.push([forecast.lat, forecast.lon]);
    }
  }
  if (points.length > 0) {
    // Establish the view BEFORE adding markers - Leaflet won't create a
    // marker's DOM element (getElement() below) until the map has one.
    map.fitBounds(points, { padding: [50, 50], animate: false });
  }

  const markers = [];
  for (const [name, forecast] of Object.entries(forecastData || {})) {
    if (forecast.lat === undefined || forecast.lon === undefined) continue;

    const current = forecast.current || {};
    const precip = forecast.periods?.[0]?.precipitationAmountIn ?? 0;
    const snowLevel = current.snow_level_ft !== null && current.snow_level_ft !== undefined
      ? `${current.snow_level_ft.toLocaleString()}'`
      : "—";
    const elevation = forecast.elevation_ft !== undefined ? `${forecast.elevation_ft.toLocaleString()}'` : "—";
    const temp = current.temp_f !== null && current.temp_f !== undefined ? `${current.temp_f}°F` : "—";
    const windSpeed = current.wind_speed_mph !== null && current.wind_speed_mph !== undefined
      ? `${current.wind_speed_mph} mph`
      : "—";
    const windDir = degToCompass(current.wind_direction_deg);

    const seed = SEED_OFFSETS[name] || DEFAULT_OFFSET;

    const icon = L.divIcon({
      className: "map-marker-wrapper",
      html: `
        <div class="true-dot"></div>
        <div class="leader-line"></div>
        <div class="callout-card">
          <div class="callout-row"><span class="callout-name">${name}</span><span class="callout-dim">, ${elevation}</span></div>
          <div class="callout-row">${directionArrowSvg(current.wind_direction_deg, 12)}<span>${windDir}, ${windSpeed}, ${temp}</span></div>
          <div class="callout-row callout-dim">&#10052;${snowLevel}, &#128167;${precip.toFixed(2)}"</div>
        </div>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    });

    const leafletMarker = L.marker([forecast.lat, forecast.lon], { icon }).addTo(map);
    const wrapperEl = leafletMarker.getElement();
    markers.push({
      dx: seed.dx,
      dy: seed.dy,
      seedDx: seed.dx,
      seedDy: seed.dy,
      lineEl: wrapperEl.querySelector(".leader-line"),
      cardEl: wrapperEl.querySelector(".callout-card"),
    });
  }

  // On narrow (phone-width) viewports the fixed-pixel leader-line offsets
  // above can push a card past the edge of the map entirely - resolving
  // overlaps between cards doesn't stop them drifting off the visible area,
  // so a card can end up fully clipped/invisible instead of just crowded.
  // Nudges any card back inward so it stays fully within the visible map
  // area (mapWrap, not the taller #map div - anything below mapWrap's crop
  // line is clipped and invisible anyway).
  function clampToMapBounds(markers) {
    const bounds = mapWrap.getBoundingClientRect();
    const margin = 4;
    for (const m of markers) {
      const rect = m.cardEl.getBoundingClientRect();
      let shiftX = 0, shiftY = 0;
      if (rect.left < bounds.left + margin) shiftX = (bounds.left + margin) - rect.left;
      else if (rect.right > bounds.right - margin) shiftX = (bounds.right - margin) - rect.right;
      if (rect.top < bounds.top + margin) shiftY = (bounds.top + margin) - rect.top;
      else if (rect.bottom > bounds.bottom - margin) shiftY = (bounds.bottom - margin) - rect.bottom;
      if (shiftX || shiftY) {
        m.dx += shiftX;
        m.dy += shiftY;
        updateCalloutPosition(m);
      }
    }
  }

  // Panning alone doesn't change cards' relative pixel spacing (the whole
  // marker layer translates together), but zooming does - points spread
  // apart when zooming in and compress when zooming out, so a layout that's
  // overlap-free at one zoom level can start overlapping at another. Re-run
  // the full reset-to-seed + resolve pass on every zoom/move so cards stay
  // clear of each other at whatever view the user pans/zooms to, instead of
  // only ever being correct for the initial auto-fit view. The bounds clamp
  // runs last since resolving overlaps can itself push a card back off the
  // edge it was just pulled in from.
  function layoutMarkers() {
    for (const m of markers) {
      m.dx = m.seedDx;
      m.dy = m.seedDy;
      updateCalloutPosition(m);
    }
    resolveCardOverlaps(markers);
    clampToMapBounds(markers);
    // Clamping a crowded card back inward can reintroduce an overlap the
    // first pass already resolved (and vice versa) - a second pass lets
    // the two converge instead of leaving whichever ran last as the final
    // (possibly still slightly off) word.
    resolveCardOverlaps(markers);
    clampToMapBounds(markers);
  }

  layoutMarkers();
  map.on("zoomend moveend", layoutMarkers);
  window.addEventListener("resize", debounce(() => {
    map.invalidateSize();
    layoutMarkers();
  }, 200));
}

function webcamFigure(label, webcam) {
  // webcam is normally {src, link} - a plain string is still accepted for
  // any caller that hasn't been given a link to the original site yet.
  const src = typeof webcam === "string" ? webcam : webcam.src;
  const link = typeof webcam === "string" ? null : webcam.link;

  const fig = document.createElement("figure");
  const isVideo = src.includes("youtube.com");
  const media = isVideo ? document.createElement("iframe") : document.createElement("img");
  media.src = src;
  if (!isVideo) {
    media.alt = label;
    media.loading = "lazy";
  }

  if (link && !isVideo) {
    // Images can be wrapped whole - clicking anywhere on the still opens
    // the original webcam page.
    const anchor = document.createElement("a");
    anchor.href = link;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.appendChild(media);
    fig.appendChild(anchor);
  } else {
    fig.appendChild(media);
  }

  const figcaption = el("figcaption", null, label);
  if (link && isVideo) {
    // An iframe intercepts clicks, so a live-stream embed can't be wrapped
    // in a link the way a still image can - surface it next to the caption.
    figcaption.appendChild(document.createTextNode(" "));
    const anchor = document.createElement("a");
    anchor.href = link;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.className = "webcam-link";
    anchor.textContent = "View on site ↗";
    figcaption.appendChild(anchor);
  }
  fig.appendChild(figcaption);
  return fig;
}

function webcamGrid(webcams) {
  const grid = el("div", "webcam-grid");
  for (const [label, webcam] of Object.entries(webcams || {})) {
    if (!webcam) continue;
    grid.appendChild(webcamFigure(label, webcam));
  }
  return grid;
}

function renderForecastSection(container, forecastData) {
  const section = el("section");
  section.appendChild(el("h2", null, "Weather Forecast (NWS)"));
  if (forecastData?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${forecastData.error}`));
    container.appendChild(section);
    return;
  }

  const locations = Object.entries(forecastData || {});
  if (locations.length === 0) {
    container.appendChild(section);
    return;
  }

  // Periods are already ~12hr blocks (day/night), so they double as the
  // table's time-increment columns. All locations are pulled around the
  // same time so period names line up, but lengths can differ slightly -
  // use the longest one for the header row.
  let headerPeriods = locations[0][1].periods;
  for (const [, forecast] of locations) {
    if (forecast.periods.length > headerPeriods.length) headerPeriods = forecast.periods;
  }

  const wrap = el("div", "forecast-table-wrap");
  const table = document.createElement("table");
  table.className = "forecast-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  headRow.appendChild(el("th", "corner", "Location"));
  for (const period of headerPeriods) {
    headRow.appendChild(el("th", null, period.name));
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const [location, forecast] of locations) {
    const row = document.createElement("tr");
    const nameCell = el("th", "row-label");
    const nameLink = document.createElement("a");
    nameLink.href = `https://forecast.weather.gov/MapClick.php?lat=${forecast.lat}&lon=${forecast.lon}`;
    nameLink.target = "_blank";
    nameLink.rel = "noopener noreferrer";
    nameLink.textContent = location;
    nameCell.appendChild(nameLink);
    nameCell.appendChild(el("div", "sub", `${forecast.elevation_ft.toLocaleString()} ft`));
    row.appendChild(nameCell);

    for (let i = 0; i < headerPeriods.length; i++) {
      const period = forecast.periods[i];
      const cell = document.createElement("td");
      if (period) {
        cell.appendChild(el("div", "cell-temp", `${period.temperature}°${period.temperatureUnit}`));
        cell.appendChild(el("div", "cell-sub", `${period.windSpeed} ${period.windDirection}`));
        cell.appendChild(el("div", "cell-sub", `💧${(period.precipitationAmountIn ?? 0).toFixed(2)}"`));
        cell.appendChild(el("div", "cell-sub", `❄${period.snowLevelFt !== null && period.snowLevelFt !== undefined ? period.snowLevelFt.toLocaleString() + "'" : "—"}`));
      } else {
        cell.textContent = "—";
      }
      row.appendChild(cell);
    }
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  section.appendChild(wrap);
  container.appendChild(section);
}

function renderSatelliteSection(container, satelliteData) {
  const section = el("section");
  section.appendChild(el("h2", null, "Satellite (GOES-West, Band 13 IR)"));
  if (satelliteData?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${satelliteData.error}`));
    container.appendChild(section);
    return;
  }

  const grid = el("div", "satellite-grid");
  for (const [name, info] of Object.entries(satelliteData || {})) {
    const fig = document.createElement("figure");
    const img = document.createElement("img");
    img.src = info.url;
    img.alt = name;
    img.loading = "lazy";
    fig.appendChild(img);

    const caption = el("figcaption", null, name);
    if (info.last_modified) {
      caption.appendChild(el("div", "sub", `Image time: ${new Date(info.last_modified).toLocaleString()}`));
    }
    fig.appendChild(caption);
    grid.appendChild(fig);
  }
  section.appendChild(grid);
  container.appendChild(section);
}

function renderGfsSnowfallSection(container, gfsData) {
  const section = el("section");
  section.appendChild(el("h2", null, "GFS 72-Hour Snowfall Forecast (Pacific NW)"));
  if (!gfsData || gfsData.error || !gfsData.path) {
    section.appendChild(el("p", "error-text", `Failed to load: ${gfsData?.error ?? "no data"}`));
    container.appendChild(section);
    return;
  }

  const hours = gfsData.forecast_hours || [];
  const lastHour = hours[hours.length - 1] ?? 72;
  const runTime = gfsData.cycle_run_at ? new Date(gfsData.cycle_run_at).toLocaleString() : "—";
  section.appendChild(el("p", "sub",
    `NOAA/NCEP's raw GFS model "snow depth change" forecast (mag.ncep.noaa.gov), cropped to the ` +
    `Pacific Northwest - Oregon isn't offered as its own region upstream, only whole-CONUS or ` +
    `broader Pacific views, so this is a local crop of the CONUS product. Each frame is the ` +
    `cumulative total since the model run started, growing out to ${lastHour} hours. ` +
    `Model run: ${runTime}.`));

  const row = el("div", "gfs-snowfall-row");

  const img = document.createElement("img");
  img.src = `${gfsData.path}?t=${encodeURIComponent(gfsData.cycle_run_at || "")}`;
  img.alt = "GFS 72-hour snowfall forecast animation, Pacific Northwest";
  img.className = "gfs-snowfall-img";
  row.appendChild(img);

  if (gfsData.legend_path) {
    const legendImg = document.createElement("img");
    // Real crop of MAG's own legend graphic, not a rebuilt approximation -
    // same cycle-freshness cache-busting as the main GIF.
    legendImg.src = `${gfsData.legend_path}?t=${encodeURIComponent(gfsData.cycle_run_at || "")}`;
    legendImg.alt = "Snowfall total legend, inches";
    legendImg.className = "gfs-snowfall-legend-img";
    row.appendChild(legendImg);
  }

  section.appendChild(row);
  container.appendChild(section);
}

function renderSnotelSection(container, snotelData) {
  const section = el("section");
  section.appendChild(el("h2", null, "Snow Depth (SNOTEL)"));
  if (snotelData?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${snotelData.error}`));
    container.appendChild(section);
    return;
  }

  const grid = el("div", "card-grid");
  for (const [station, readings] of Object.entries(snotelData || {})) {
    const card = el("div", "card");
    card.appendChild(el("h3", null, station));

    const depth = readings.snow_depth_in;
    if (depth !== undefined) {
      card.appendChild(el("div", "big-temp", `${depth}"`));
      card.appendChild(el("div", "sub", `Snow depth, as of ${readings.snow_depth_in_date}`));
    } else {
      card.appendChild(el("div", "sub", "No snow depth reading"));
    }

    const change12h = formatSnowDelta(readings.change_12h_in);
    const change24h = formatSnowDelta(readings.change_24h_in);
    card.appendChild(statRow("12 hr change", change12h.text, change12h.cls));
    card.appendChild(statRow("24 hr change", change24h.text, change24h.cls));

    if (readings.swe_in !== undefined) {
      card.appendChild(statRow("Snow water equiv.", `${readings.swe_in}"`));
    }
    grid.appendChild(card);
  }
  section.appendChild(grid);
  container.appendChild(section);
}

function renderMtBachelor(container, data) {
  const section = el("section");
  section.appendChild(el("h2", null, "Mt. Bachelor"));
  if (data?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${data.error}`));
    container.appendChild(section);
    return;
  }

  const current = data.weather?.current;
  if (current) {
    section.appendChild(el("div", "big-temp", `${current.temperature}°F`));
  }

  const grid = el("div", "card-grid");
  for (const [key, sensor] of Object.entries(data.weather?.sensors || {})) {
    const card = el("div", "card");
    card.appendChild(el("h3", null, sensor.display_name || key));
    if (sensor.elevation_ft) {
      card.appendChild(el("div", "sub", `${sensor.elevation_ft.toLocaleString()} ft`));
    }
    card.appendChild(el("div", "big-temp", sensor.temperature ? `${Math.round(sensor.temperature)}°F` : "—"));
    if (sensor.wind?.direction) {
      card.appendChild(statRow("Wind direction", sensor.wind.direction));
    }
    card.appendChild(statRow("Wind avg", `${sensor.wind?.average ?? "—"} mph`));
    card.appendChild(statRow("Wind max", `${sensor.wind?.high ?? "—"} mph`));
    grid.appendChild(card);
  }
  section.appendChild(grid);

  const computed = data.latest_report?.computed;
  if (computed) {
    const statsCard = el("div", "card");
    statsCard.appendChild(el("h3", null, "Snow Totals"));
    statsCard.appendChild(statRow("24 hr", `${computed["24_hour"]}"`));
    statsCard.appendChild(statRow("48 hr", `${computed["48_hour"]}"`));
    statsCard.appendChild(statRow("7 day", `${computed["7_day"]}"`));
    statsCard.appendChild(statRow("Base depth", `${data.latest_report.base_depth}"`));
    statsCard.appendChild(statRow("Season total", `${computed["total"]}"`));
    section.appendChild(statsCard);
  }

  section.appendChild(webcamGrid(data.webcams));
  container.appendChild(section);
}

function renderHoodoo(container, data) {
  const section = el("section");
  section.appendChild(el("h2", null, "Hoodoo"));
  if (data?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${data.error}`));
    container.appendChild(section);
    return;
  }

  const w = data.weather || {};
  const card = el("div", "card");
  if (w["Temperature"]) {
    card.appendChild(el("div", "big-temp", decodeDegrees(w["Temperature"].split("\n")[0])));
  }
  if (w["Wind"]) card.appendChild(statRow("Wind", w["Wind"]));
  if (w["Snow depth"]) card.appendChild(statRow("Snow depth", w["Snow depth"]));
  if (w["Humidity"]) card.appendChild(statRow("Humidity", w["Humidity"]));
  section.appendChild(card);

  const totals = data.snow_totals;
  if (totals) {
    const statsCard = el("div", "card");
    statsCard.appendChild(el("h3", null, "Snow Totals"));
    const trend = totals.trend || {};
    if (trend["24 Hr"]) statsCard.appendChild(statRow("24 hr change", trend["24 Hr"]));
    if (trend["12 Hr"]) statsCard.appendChild(statRow("12 hr change", trend["12 Hr"]));
    if (trend["6 Hr"]) statsCard.appendChild(statRow("6 hr change", trend["6 Hr"]));
    if (w["Snow depth"]) statsCard.appendChild(statRow("Base depth", w["Snow depth"]));
    if (totals.season_total_in !== null && totals.season_total_in !== undefined) {
      statsCard.appendChild(statRow("Season total", `${totals.season_total_in}"`));
    }
    section.appendChild(statsCard);
  }

  section.appendChild(webcamGrid(data.webcams));
  container.appendChild(section);
}

function renderWillamettePass(container, data) {
  const section = el("section");
  section.appendChild(el("h2", null, "Willamette Pass"));
  if (data?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${data.error}`));
    container.appendChild(section);
    return;
  }

  const f = data.forecast || {};
  if (f.current_temperature) {
    section.appendChild(el("div", "big-temp", `${f.current_temperature}°F`));
    section.appendChild(el("div", "sub", f.current_weather));
  }

  const totals = data.snow_totals || {};
  const statsCard = el("div", "card");
  statsCard.appendChild(el("h3", null, "Snow Totals"));
  for (const [label, value] of Object.entries(totals)) {
    statsCard.appendChild(statRow(label, value));
  }
  section.appendChild(statsCard);

  section.appendChild(webcamGrid(data.webcams));
  container.appendChild(section);
}

function renderSnowStakeCams(container, snowStakeData) {
  const section = el("section");
  section.appendChild(el("h2", null, "Snow Stake Cameras"));
  if (snowStakeData?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${snowStakeData.error}`));
    container.appendChild(section);
    return;
  }
  section.appendChild(el("p", "sub", "Base-area views at all three resorts, side by side."));
  section.appendChild(webcamGrid(snowStakeData));
  container.appendChild(section);
}

function renderOdotCams(container, camsData) {
  const section = el("section");
  section.appendChild(el("h2", null, "Road Cams (ODOT)"));
  if (camsData?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${camsData.error}`));
    container.appendChild(section);
    return;
  }

  for (const [route, cams] of Object.entries(camsData || {})) {
    section.appendChild(el("h3", null, route));
    const webcams = {};
    for (const cam of cams) {
      webcams[`${cam["device-name"]} (MP ${cam.milepoint})`] = { src: cam["cctv-url"], link: cam["tripcheck_link"] };
    }
    section.appendChild(webcamGrid(webcams));
  }
  container.appendChild(section);
}

function dangerBadge(danger) {
  if (!danger || danger.length === 0) {
    return el("span", "danger-badge danger-none", "No rating / off-season");
  }
  const maxRating = Math.max(...danger.map((d) => d.rating || 0));
  const cls = DANGER_CLASSES[maxRating] || "danger-none";
  const label = DANGER_LABELS[maxRating] || "Unknown";
  return el("span", `danger-badge ${cls}`, label);
}

function stripHtml(html) {
  const div = document.createElement("div");
  div.innerHTML = html || "";
  return div.textContent || "";
}

function renderAvalanche(container, avalancheData) {
  const section = el("section");
  section.appendChild(el("h2", null, "Avalanche Advisory (COAC)"));
  if (avalancheData?.error) {
    section.appendChild(el("p", "error-text", `Failed to load: ${avalancheData.error}`));
    container.appendChild(section);
    return;
  }

  const grid = el("div", "card-grid");
  for (const [zone, forecast] of Object.entries(avalancheData || {})) {
    const card = el("div", "card");
    card.appendChild(el("h3", null, zone));
    card.appendChild(dangerBadge(forecast.danger));
    card.appendChild(el("div", "sub", `Published: ${forecast.published_time}`));

    const summary = stripHtml(forecast.bottom_line);
    const bottomLine = el("div", "bottom-line", summary.slice(0, 400) + (summary.length > 400 ? "..." : ""));
    card.appendChild(bottomLine);

    grid.appendChild(card);
  }
  section.appendChild(grid);
  container.appendChild(section);
}

async function main() {
  const app = document.getElementById("app");
  try {
    const resp = await fetch("conditions.json");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    document.getElementById("updated-at").textContent =
      `Last updated: ${new Date(data.generated_at).toLocaleString()}`;

    app.innerHTML = "";
    renderSummarySection(app, data);
    renderWindRoseSection(app, data.wind_roses);
    renderBachelorTimeseries(app, data.bachelor_timeseries);
    renderMapSection(app, data.forecast);
    renderForecastSection(app, data.forecast);
    renderSatelliteSection(app, data.satellite);
    renderGfsSnowfallSection(app, data.gfs_snowfall);
    renderSnotelSection(app, data.snotel);
    renderSnowStakeCams(app, data.snow_stake_cams);
    renderMtBachelor(app, data.mtbachelor);
    renderHoodoo(app, data.hoodoo);
    renderWillamettePass(app, data.willamette_pass);
    renderOdotCams(app, data.odot_cams);
    renderAvalanche(app, data.avalanche);
  } catch (err) {
    app.innerHTML = "";
    app.appendChild(el("p", "error-text",
      `Couldn't load conditions.json: ${err.message}. Are you serving this over a local ` +
      `web server (not opening the file directly)?`));
  }
}

function initFeedbackForm() {
  const form = document.getElementById("feedback-form");
  const status = document.getElementById("feedback-status");
  if (!form || !status) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    status.textContent = "Sending...";

    try {
      const resp = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
      });
      if (resp.ok) {
        form.reset();
        status.textContent = "Thanks - your feedback was sent!";
      } else {
        status.textContent = "Something went wrong - try again, or email brian.butcher.91@gmail.com directly.";
        submitBtn.disabled = false;
      }
    } catch {
      status.textContent = "Something went wrong - try again, or email brian.butcher.91@gmail.com directly.";
      submitBtn.disabled = false;
    }
  });
}

main();
initFeedbackForm();
