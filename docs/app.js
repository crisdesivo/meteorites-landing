/* Interactive meteorite map: Leaflet basemap + one canvas layer for ~32k points.
 * Data comes from data/meteorites.js (window.METEORITES), written by build.py. */
(function () {
  "use strict";

  const D = window.METEORITES;
  const N = D.name.length;

  const FOUND = "#3987e5";
  const FELL = "#d95926";
  const NO_YEAR = "#6b6a66";
  // Single-hue ramp for year (dark = older, light = recent).
  const RAMP = [[1800, "#184f95"], [1950, "#2a78d6"], [1985, "#6da7ec"], [2013, "#cde2fb"]];
  const MASS_STEPS = [0, 10, 100, 1e3, 1e4, 1e5, 1e6, 1e7]; // grams
  const YEAR_LO = 1800, YEAR_HI = 2013;

  const state = {
    yearMin: YEAR_LO, yearMax: YEAR_HI, massStep: 0,
    found: true, fell: true, groups: new Set(D.groups.map((_, i) => i)),
    color: "fall",
  };

  // ---------- helpers ----------
  const $ = (id) => document.getElementById(id);
  const fmtInt = (n) => n.toLocaleString("en-US");
  function fmtMass(g) {
    if (g == null) return "unknown";
    if (g >= 1e6) return (g / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 }) + " t";
    if (g >= 1e3) return (g / 1e3).toLocaleString("en-US", { maximumFractionDigits: 1 }) + " kg";
    return g.toLocaleString("en-US", { maximumFractionDigits: 1 }) + " g";
  }
  function hexToRgb(h) { const v = parseInt(h.slice(1), 16); return [v >> 16, (v >> 8) & 255, v & 255]; }
  const RAMP_RGB = RAMP.map(([y, c]) => [y, hexToRgb(c)]);
  function yearColor(y) {
    if (y == null) return NO_YEAR;
    if (y <= RAMP_RGB[0][0]) return RAMP[0][1];
    for (let i = 1; i < RAMP_RGB.length; i++) {
      const [y1, c1] = RAMP_RGB[i];
      if (y <= y1) {
        const [y0, c0] = RAMP_RGB[i - 1];
        const t = Math.round(((y - y0) / (y1 - y0)) * 8) / 8; // 8 buckets per segment
        const c = c0.map((v, k) => Math.round(v + (c1[k] - v) * t));
        return `rgb(${c[0]},${c[1]},${c[2]})`;
      }
    }
    return RAMP[RAMP.length - 1][1];
  }
  const baseRadius = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const m = D.mass[i];
    baseRadius[i] = 0.7 + 0.55 * Math.log10((m == null ? 1 : m) + 1);
  }
  const yearColors = D.year.map(yearColor);

  // ---------- map ----------
  // No tile server: land and borders ship with the page (data/basemap.js),
  // so the map works offline, from file:// and on GitHub Pages without keys.
  const map = L.map("map", {
    center: [20, 10], zoom: 2, minZoom: 2, maxZoom: 10,
    maxBounds: [[-89, -200], [89, 200]], maxBoundsViscosity: 1,
    preferCanvas: true, zoomControl: true, attributionControl: true,
  });
  map.attributionControl.setPrefix(false).addAttribution(
    'Land: <a href="https://www.naturalearthdata.com/">Natural Earth</a> · ' +
    'Data: <a href="https://data.nasa.gov/dataset/meteorite-landings">NASA</a> · ' +
    '<a href="https://leafletjs.com">Leaflet</a>');
  const basemap = L.canvas({ padding: 0.5 });
  L.geoJSON(window.BASEMAP.land, {
    renderer: basemap, interactive: false,
    style: { stroke: true, color: "#3a414c", weight: 0.6, fillColor: "#1f242c", fillOpacity: 1 },
  }).addTo(map);
  L.geoJSON(window.BASEMAP.borders, {
    renderer: basemap, interactive: false,
    style: { color: "#323843", weight: 0.6 },
  }).addTo(map);

  // ---------- canvas layer ----------
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:absolute;left:0;top:0;pointer-events:none;z-index:450";
  map.getContainer().appendChild(canvas);
  const ctx = canvas.getContext("2d");

  const visible = new Uint8Array(N);
  let projZoom = null;
  const px = new Float64Array(N), py = new Float64Array(N);

  function project() {
    const z = map.getZoom();
    if (z === projZoom) return;
    for (let i = 0; i < N; i++) {
      const p = map.project([D.lat[i], D.lon[i]], z);
      px[i] = p.x; py[i] = p.y;
    }
    projZoom = z;
  }

  function radiusScale() { return 1 + 0.3 * (map.getZoom() - 2); }

  function draw() {
    const size = map.getSize(), dpr = window.devicePixelRatio || 1;
    if (canvas.width !== size.x * dpr || canvas.height !== size.y * dpr) {
      canvas.width = size.x * dpr; canvas.height = size.y * dpr;
      canvas.style.width = size.x + "px"; canvas.style.height = size.y + "px";
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);
    project();
    const origin = map.getPixelBounds().min;
    const k = radiusScale();

    // Batch points per colour; insertion order keeps big rocks first and falls on top.
    const batches = new Map();
    for (let i = 0; i < N; i++) {
      if (!visible[i]) continue;
      const r = baseRadius[i] * k;
      const x = px[i] - origin.x, y = py[i] - origin.y;
      if (x < -r || x > size.x + r || y < -r || y > size.y + r) continue;
      const color = state.color === "fall" ? (D.fell[i] ? FELL : FOUND) : yearColors[i];
      let b = batches.get(color);
      if (!b) { b = new Path2D(); batches.set(color, b); }
      b.moveTo(x + r, y);
      b.arc(x, y, r, 0, 2 * Math.PI);
    }
    const order = [...batches.keys()].sort((a, b) => (a === FELL) - (b === FELL));
    for (const color of order) {
      ctx.globalAlpha = color === FELL ? 0.9 : 0.6;
      ctx.fillStyle = color;
      ctx.fill(batches.get(color));
    }
    ctx.globalAlpha = 1;
  }

  // Pans and flyTo frames redraw directly; CSS-animated zooms (wheel, +/-) hide
  // the canvas for the ~250 ms animation and redraw once it ends.
  map.on("move resize zoom", draw);
  map.on("zoomanim", () => { canvas.style.opacity = 0; });
  map.on("zoomend", () => { draw(); canvas.style.opacity = 1; });

  // ---------- filtering ----------
  function applyFilters() {
    const minMass = MASS_STEPS[state.massStep];
    const fullYears = state.yearMin === YEAR_LO && state.yearMax === YEAR_HI;
    let shown = 0, fell = 0, mass = 0;
    for (let i = 0; i < N; i++) {
      let ok = (D.fell[i] ? state.fell : state.found) && state.groups.has(D.group[i]);
      if (ok && minMass > 0) ok = D.mass[i] != null && D.mass[i] >= minMass;
      if (ok && !fullYears) {
        const y = D.year[i];
        ok = y != null && (state.yearMin === YEAR_LO || y >= state.yearMin) && y <= state.yearMax;
      }
      visible[i] = ok ? 1 : 0;
      if (ok) { shown++; fell += D.fell[i]; mass += D.mass[i] || 0; }
    }
    $("count").textContent = fmtInt(shown);
    $("breakdown").textContent =
      `${fmtInt(shown - fell)} found · ${fmtInt(fell)} fell · ${fmtMass(mass)} total`;
    draw();
  }

  // ---------- controls ----------
  const yMin = $("year-min"), yMax = $("year-max");
  for (const el of [yMin, yMax]) { el.min = YEAR_LO; el.max = YEAR_HI; el.step = 1; }
  yMin.value = YEAR_LO; yMax.value = YEAR_HI;
  function onYears(e) {
    let a = +yMin.value, b = +yMax.value;
    if (a > b) { if (e && e.target === yMin) b = a; else a = b; yMin.value = a; yMax.value = b; }
    state.yearMin = a; state.yearMax = b;
    $("year-label").textContent = (a === YEAR_LO && b === YEAR_HI) ? "all years"
      : `${a === YEAR_LO ? "≤ " + YEAR_LO : a} – ${b}`;
    applyFilters();
  }
  yMin.addEventListener("input", onYears);
  yMax.addEventListener("input", onYears);

  const massLabels = ["any", "≥ 10 g", "≥ 100 g", "≥ 1 kg", "≥ 10 kg", "≥ 100 kg", "≥ 1 t", "≥ 10 t"];
  $("mass").addEventListener("input", (e) => {
    state.massStep = +e.target.value;
    $("mass-label").textContent = massLabels[state.massStep];
    applyFilters();
  });

  $("found").addEventListener("change", (e) => { state.found = e.target.checked; applyFilters(); });
  $("fell").addEventListener("change", (e) => { state.fell = e.target.checked; applyFilters(); });

  const groupCounts = D.groups.map(() => 0);
  for (let i = 0; i < N; i++) groupCounts[D.group[i]]++;
  const groupBoxes = D.groups.map((g, gi) => {
    const label = document.createElement("label");
    label.className = "check";
    label.innerHTML = `<input type="checkbox" checked data-g="${gi}"><span>${g}</span><span class="n">${fmtInt(groupCounts[gi])}</span>`;
    const box = label.querySelector("input");
    box.addEventListener("change", () => {
      box.checked ? state.groups.add(gi) : state.groups.delete(gi);
      $("groups-toggle").textContent = state.groups.size ? "none" : "all";
      applyFilters();
    });
    $("groups").appendChild(label);
    return box;
  });
  $("groups-toggle").addEventListener("click", () => {
    const all = state.groups.size === 0;
    groupBoxes.forEach((b, gi) => { b.checked = all; all ? state.groups.add(gi) : state.groups.delete(gi); });
    $("groups-toggle").textContent = all ? "none" : "all";
    applyFilters();
  });

  document.querySelectorAll('input[name="color"]').forEach((r) =>
    r.addEventListener("change", (e) => {
      state.color = e.target.value;
      $("year-legend").hidden = state.color !== "year";
      draw();
    }));

  // ---------- details popup ----------
  // Many finds are recorded at the coordinates of the ice field or desert area
  // they came from, so thousands can share one dot.
  function stackCount(i) {
    let n = 0;
    for (let j = 0; j < N; j++) if (visible[j] && D.lat[j] === D.lat[i] && D.lon[j] === D.lon[i]) n++;
    return n;
  }
  function popupHtml(i) {
    const stack = stackCount(i);
    const row = (k, v) => `<tr><td>${k}</td><td>${v}</td></tr>`;
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    return `<h3>${esc(D.name[i])}</h3><table>` +
      row("Class", `${esc(D.classes[D.cls[i]])} <span style="color:#8a8984">(${D.groups[D.group[i]]})</span>`) +
      row("Mass", fmtMass(D.mass[i])) +
      row(D.fell[i] ? "Fell" : "Found", D.year[i] ?? "year unknown") +
      row("Location", `${D.lat[i].toFixed(3)}, ${D.lon[i].toFixed(3)}`) +
      `</table>` +
      (stack > 1 ? `<p style="margin:8px 0 0;color:#c3c2b7">${fmtInt(stack - 1)} more shown at this exact spot</p>` : "") +
      `<p style="margin:8px 0 0"><a href="https://www.lpi.usra.edu/meteor/metbull.php?code=${D.id[i]}" target="_blank" rel="noopener">Meteoritical Bulletin entry ↗</a></p>`;
  }
  function openPopup(i) {
    L.popup({ maxWidth: 320 }).setLatLng([D.lat[i], D.lon[i]]).setContent(popupHtml(i)).openOn(map);
  }

  map.on("click", (e) => {
    project();
    const origin = map.getPixelBounds().min;
    const cx = e.containerPoint.x, cy = e.containerPoint.y, k = radiusScale();
    let best = -1, bestD = Infinity;
    for (let i = 0; i < N; i++) {
      if (!visible[i]) continue;
      const dy = py[i] - origin.y - cy;
      if (Math.abs(dy) > 20) continue;
      const d = Math.hypot(px[i] - origin.x - cx, dy);
      if (d <= baseRadius[i] * k + 5 && d < bestD) { bestD = d; best = i; }
    }
    if (best >= 0) openPopup(best);
  });

  // ---------- search ----------
  const lowerNames = D.name.map((s) => s.toLowerCase());
  const search = $("search"), list = $("names");
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    list.innerHTML = "";
    if (q.length < 2) return;
    let n = 0;
    for (let i = 0; i < N && n < 12; i++) {
      if (lowerNames[i].startsWith(q)) {
        const o = document.createElement("option"); o.value = D.name[i]; list.appendChild(o); n++;
      }
    }
  });
  function goTo(q) {
    q = q.trim().toLowerCase();
    if (!q) return;
    let i = lowerNames.indexOf(q);
    if (i < 0) i = lowerNames.findIndex((s) => s.startsWith(q));
    if (i < 0) i = lowerNames.findIndex((s) => s.includes(q));
    if (i < 0) { search.setCustomValidity("No meteorite with that name"); search.reportValidity(); return; }
    search.setCustomValidity("");
    map.setView([D.lat[i], D.lon[i]], Math.max(map.getZoom(), 6));
    openPopup(i);
  }
  search.addEventListener("change", () => goTo(search.value));
  search.addEventListener("keydown", (e) => { if (e.key === "Enter") goTo(search.value); });

  // ---------- quick views ----------
  const VIEWS = {
    world: [[20, 10], 2],
    antarctica: [[-80, 90], 3],   // Allan Hills, Yamato, Grove Mountains...
    sahara: [[25, 5], 4],         // NW Africa and Libyan desert finds
    oman: [[19.5, 55.5], 6],      // Dhofar
  };
  document.querySelectorAll("#views button").forEach((b) =>
    b.addEventListener("click", () => {
      const [center, zoom] = VIEWS[b.dataset.view];
      map.closePopup();
      map.flyTo(center, zoom, { duration: 1.6 });
    }));

  // Small hook so the demo recorder (scripts/record_demo.py) can drive the page.
  window.meteoriteMap = { map, state, applyFilters, goTo };

  onYears();
  $("mass-label").textContent = massLabels[0];
  $("loading").hidden = true;
})();
