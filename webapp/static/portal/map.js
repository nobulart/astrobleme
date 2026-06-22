const defaultPreferences = {
  center: [5, 15], zoom: 2, layers: ["study-candidates", "my-candidates"],
  basemap: "street", rasters: [], rasterOpacity: 68, satelliteDate: "", candidateDraft: null,
  scoreField: "followup_score", palette: "turbo", drawingMethod: "center-radius"
};
const savedPreferences = JSON.parse(document.getElementById("map-preferences")?.textContent || "{}");
let preferences = {...defaultPreferences, ...savedPreferences};
const map = L.map("map", {worldCopyJump: true, zoomControl: false}).setView(preferences.center, preferences.zoom);
L.control.zoom({position: "bottomright"}).addTo(map);
const streetLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18, attribution: "© OpenStreetMap contributors"}).addTo(map);

const palette = {
  "study-candidates": {color: "#e6a94a", weight: 1.4, opacity: .7},
  "repaired-catalogue": {color: "#73c6b6", weight: 2, radius: 5},
  "african-structures": {color: "#f1e6c8", weight: 2, radius: 5},
  "negative-controls": {color: "#e36f5b", weight: 2, fillOpacity: .18},
  "active-faults": {color: "#9b6bc6", weight: .8, opacity: .55},
  community: {color: "#ff6f61", weight: 2.5, radius: 7},
  "my-candidates": {color: "#55d6be", weight: 3, radius: 8, fillOpacity: .65},
  "other-candidates": {color: "#ff8b7e", weight: 2.2, radius: 7, fillOpacity: .45}
};
const loaded = {}, groups = {};
const status = document.getElementById("map-status");
const resetCallbacks = [];
let saveTimer, suspendPersistence = true, activeBasemapSlug = "street", activeRasterSlugs = new Set();
let candidateDraft = preferences.candidateDraft;
const scientificPalettes = {
  turbo: ["#30123b", "#4666e8", "#1bcfd4", "#65fe62", "#d6e935", "#f99217", "#7a0403"],
  viridis: ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
  plasma: ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"],
  inferno: ["#000004", "#420a68", "#932667", "#dd513a", "#fca50a", "#fcffa4"],
  magma: ["#000004", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"],
  cividis: ["#00204c", "#414d6b", "#7d7c78", "#b9ac70", "#ffea46"],
  rdbu: ["#67001f", "#d6604d", "#f7f7f7", "#4393c3", "#053061"]
};

function esc(value) { const d = document.createElement("div"); d.textContent = value ?? "—"; return d.innerHTML; }
function propsFor(feature) {
  const p = feature.properties || {};
  return {
    title: p.candidate_id || p.title || p.display_name || p.name || p.Name || "Map feature",
    score: p.followup_score ?? p.intake_score,
    scoreLabel: p.followup_score != null ? "Follow-up score" : p.intake_score != null ? "Intake score" : null,
    diameter: p.diameter_km ?? p.structure_diameter_km ?? p.diameter_max_km,
    status: p.review_tier || p.status || p.confirmed_raw || p.Type,
    note: p.score_interpretation || p.geometry_interpretation || p.Description || p.observed_feature,
    searchable: JSON.stringify(p).toLowerCase()
  };
}
function popup(feature) {
  const p = propsFor(feature);
  return `<div class="map-popup"><strong>${esc(p.title)}</strong>${p.scoreLabel ? `<span>${p.scoreLabel}: ${Number(p.score).toFixed(3)}</span>` : ""}${p.diameter ? `<span>Diameter: ${Number(p.diameter).toFixed(1)} km</span>` : ""}${p.status ? `<span>Status/tier: ${esc(p.status)}</span>` : ""}${p.note ? `<p>${esc(p.note)}</p>` : ""}</div>`;
}
function mixColour(a, b, t) { const n = i => parseInt(i, 16), c = (x, y) => Math.round(x + (y - x) * t).toString(16).padStart(2, "0"); return `#${c(n(a.slice(1,3)),n(b.slice(1,3)))}${c(n(a.slice(3,5)),n(b.slice(3,5)))}${c(n(a.slice(5,7)),n(b.slice(5,7)))}`; }
function paletteColour(t) { const colours = scientificPalettes[preferences.palette] || scientificPalettes.turbo, scaled = Math.max(0, Math.min(.999999, t)) * (colours.length - 1), i = Math.floor(scaled); return mixColour(colours[i], colours[i + 1], scaled - i); }
function restyleScientificLayers() {
  const values = [];
  const visibleSlugs = new Set(Array.from(document.querySelectorAll("[data-layer]:checked"), input => input.dataset.layer));
  Object.entries(groups).forEach(([slug, group]) => {
    if (!visibleSlugs.has(slug) || !map.hasLayer(group)) return;
    group.eachLayer(layer => { const raw = layer.feature?.properties?.[preferences.scoreField], value = raw === null || raw === "" || raw === undefined ? NaN : Number(raw); if (Number.isFinite(value)) values.push(value); });
  });
  const min = values.length ? Math.min(...values) : 0, max = values.length ? Math.max(...values) : 1;
  Object.entries(groups).forEach(([slug, group]) => group.eachLayer(layer => {
    if (!layer.setStyle) return;
    const sourceValue = layer.feature?.properties?.[preferences.scoreField];
    const raw = sourceValue === null || sourceValue === "" || sourceValue === undefined ? NaN : Number(sourceValue);
    const state = layer.feature?.properties?.review_status || "";
    const provisional = slug === "study-candidates" || ["baseline_passed", "under_review"].includes(state);
    const colour = Number.isFinite(raw) && values.length ? paletteColour(max === min ? .5 : (raw - min) / (max - min)) : palette[slug]?.color;
    layer.setStyle({...palette[slug], color: colour, dashArray: provisional ? "7 5" : null, fillOpacity: provisional ? .08 : (palette[slug]?.fillOpacity ?? .22)});
  }));
  const legend = document.getElementById("score-legend");
  const fieldLabel = document.querySelector(`#score-field option[value="${preferences.scoreField}"]`)?.textContent || preferences.scoreField;
  const digits = preferences.scoreField === "diameter_km" ? 1 : 3;
  if (legend) legend.innerHTML = values.length ? `<strong>${esc(fieldLabel)}</strong><span>${esc(min.toFixed(digits))}</span><i style="background:linear-gradient(90deg,${scientificPalettes[preferences.palette].join(",")})"></i><span>${esc(max.toFixed(digits))}</span><small>${values.length.toLocaleString()} displayed values · exact data range</small>` : `<strong>${esc(fieldLabel)}</strong><small>No numeric values in displayed layers</small>`;
}
async function loadLayer(slug) {
  if (loaded[slug]) return groups[slug];
  status.textContent = `Loading ${slug.replaceAll("-", " ")}…`;
  const response = await fetch(window.ASTROBLEME_LAYER_URLS[slug]);
  if (!response.ok) throw new Error(`Layer failed: ${slug}`);
  const data = await response.json();
  const style = palette[slug];
  const group = L.geoJSON(data, {
    style: () => style,
    pointToLayer: (_feature, latlng) => L.circleMarker(latlng, style),
    onEachFeature: (feature, layer) => { layer.bindPopup(popup(feature)); layer._searchText = propsFor(feature).searchable; }
  });
  loaded[slug] = true; groups[slug] = group;
  document.querySelector(`[data-count="${slug}"]`).textContent = `${data.features.length.toLocaleString()} features`;
  status.textContent = "Ready"; setTimeout(() => status.classList.add("quiet"), 900);
  return group;
}
async function setLayer(slug, enabled) {
  try { const group = await loadLayer(slug); enabled ? group.addTo(map) : map.removeLayer(group); restyleScientificLayers(); }
  catch (error) { status.textContent = error.message; status.classList.remove("quiet"); }
}
function currentPreferences() {
  const center = map.getCenter();
  return {
    center: [center.lat, center.lng], zoom: map.getZoom(),
    layers: Array.from(document.querySelectorAll("[data-layer]:checked"), input => input.dataset.layer),
    basemap: activeBasemapSlug, rasters: [...activeRasterSlugs],
    rasterOpacity: Number(document.getElementById("raster-opacity")?.value || 68),
    satelliteDate: document.getElementById("satellite-date")?.value || "",
    candidateDraft, scoreField: preferences.scoreField, palette: preferences.palette, drawingMethod: preferences.drawingMethod
  };
}
function persistPreferences() {
  if (suspendPersistence || !window.ASTROBLEME_PREFERENCE_URL) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    const csrf = document.querySelector("#map-preference-token input")?.value;
    try {
      await fetch(window.ASTROBLEME_PREFERENCE_URL, {
        method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
        body: JSON.stringify(currentPreferences())
      });
    } catch (_error) { status.textContent = "Map choices could not be saved."; status.classList.remove("quiet"); }
  }, 350);
}

document.querySelectorAll("[data-layer]").forEach(input => {
  input.checked = preferences.layers.includes(input.dataset.layer);
  input.addEventListener("change", () => { setLayer(input.dataset.layer, input.checked); persistPreferences(); });
  if (input.checked) setLayer(input.dataset.layer, true);
});
map.on("moveend", persistPreferences);
document.getElementById("map-search").addEventListener("input", event => {
  const q = event.target.value.trim().toLowerCase(); if (q.length < 3) return;
  for (const group of Object.values(groups)) for (const layer of group.getLayers()) {
    if (layer._searchText?.includes(q)) { map.fitBounds(layer.getBounds ? layer.getBounds().pad(.6) : L.latLngBounds([layer.getLatLng()])); layer.openPopup(); return; }
  }
});
const scoreField = document.getElementById("score-field"), paletteSelect = document.getElementById("map-palette");
if (scoreField) { scoreField.value = preferences.scoreField; scoreField.addEventListener("change", () => { preferences.scoreField = scoreField.value; restyleScientificLayers(); persistPreferences(); }); }
if (paletteSelect) { paletteSelect.value = preferences.palette; paletteSelect.addEventListener("change", () => { preferences.palette = paletteSelect.value; restyleScientificLayers(); persistPreferences(); }); }

if (window.ASTROBLEME_RASTER_ACCESS) {
  const sourcePanel = document.getElementById("remote-source");
  const dateInput = document.getElementById("satellite-date");
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  dateInput.value = preferences.satelliteDate || yesterday;
  dateInput.max = new Date().toISOString().slice(0, 10);
  document.getElementById("raster-opacity").value = preferences.rasterOpacity;

  const sourceInfo = {
    street: ["OpenStreetMap", "https://www.openstreetmap.org/copyright"],
    aerial: ["Esri World Imagery", "https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9"],
    satellite: ["NASA EOSDIS GIBS MODIS Terra", "https://nasa-gibs.github.io/gibs-api-docs/"],
    "gebco-elevation": ["GEBCO latest elevation/bathymetry", "https://www.gebco.net/data-products/gebco-web-services/web-map-service"],
    "gebco-tid": ["GEBCO Type Identifier grid", "https://www.gebco.net/data-products/gebco-web-services/web-map-service"],
    magnetic: ["NOAA NCEI EMAG2v3", "https://www.ncei.noaa.gov/products/earth-magnetic-model-anomaly-grid-2"]
  };
  const aerialLayer = L.tileLayer("/api/raster/tiles/aerial/{z}/{x}/{y}", {maxZoom: 18, attribution: "Esri, Maxar, Earthstar Geographics and contributors"});
  let satelliteLayer = L.tileLayer(`/api/raster/tiles/satellite/{z}/{x}/{y}?date=${dateInput.value}`, {maxZoom: 9, attribution: "NASA EOSDIS GIBS"});
  const rasterLayers = {
    "gebco-elevation": L.tileLayer.wms("/api/raster/wms/gebco-elevation", {layers: "gebco_latest", format: "image/png", transparent: true, version: "1.1.1", attribution: "GEBCO Compilation Group"}),
    "gebco-tid": L.tileLayer.wms("/api/raster/wms/gebco-tid", {layers: "gebco_latest_tid", format: "image/png", transparent: true, version: "1.1.1", attribution: "GEBCO Compilation Group"}),
    magnetic: L.tileLayer("/api/raster/tiles/magnetic/{z}/{x}/{y}", {maxZoom: 8, attribution: "NOAA NCEI"})
  };
  let activeBasemap = streetLayer;

  function showSource(slug) {
    const info = sourceInfo[slug];
    if (info) sourcePanel.innerHTML = `<strong>${esc(info[0])}</strong><br><a href="${info[1]}" target="_blank" rel="noopener">Provider documentation ↗</a><br>Streamed through the atlas allowlist; no server-side raster cache.`;
  }
  function attachRasterErrors(layer, slug) {
    layer.on("tileerror", () => { status.textContent = `${sourceInfo[slug]?.[0] || slug} is temporarily unavailable.`; status.classList.remove("quiet"); });
    return layer;
  }
  function chooseBasemap(slug) {
    map.removeLayer(activeBasemap);
    activeBasemapSlug = slug;
    activeBasemap = slug === "aerial" ? aerialLayer : slug === "satellite" ? satelliteLayer : streetLayer;
    activeBasemap.addTo(map).bringToBack();
    if (slug !== "street") showSource(slug);
  }
  attachRasterErrors(aerialLayer, "aerial"); attachRasterErrors(satelliteLayer, "satellite");
  Object.entries(rasterLayers).forEach(([slug, layer]) => attachRasterErrors(layer, slug));

  document.querySelectorAll("[data-basemap]").forEach(input => {
    input.checked = input.dataset.basemap === preferences.basemap;
    input.addEventListener("change", () => { if (input.checked) { chooseBasemap(input.dataset.basemap); persistPreferences(); } });
  });
  chooseBasemap(preferences.basemap);

  document.querySelectorAll("[data-raster]").forEach(input => {
    const slug = input.dataset.raster;
    input.checked = preferences.rasters.includes(slug);
    if (input.checked) { rasterLayers[slug].setOpacity(preferences.rasterOpacity / 100).addTo(map); activeRasterSlugs.add(slug); }
    input.addEventListener("change", () => {
      const layer = rasterLayers[slug];
      if (input.checked) { layer.setOpacity(Number(document.getElementById("raster-opacity").value) / 100).addTo(map); activeRasterSlugs.add(slug); showSource(slug); }
      else { map.removeLayer(layer); activeRasterSlugs.delete(slug); }
      persistPreferences();
    });
  });
  document.getElementById("raster-opacity").addEventListener("input", event => {
    const opacity = Number(event.target.value) / 100;
    activeRasterSlugs.forEach(slug => rasterLayers[slug].setOpacity(opacity)); persistPreferences();
  });
  dateInput.addEventListener("change", () => {
    const wasActive = map.hasLayer(satelliteLayer);
    if (wasActive) map.removeLayer(satelliteLayer);
    satelliteLayer = attachRasterErrors(L.tileLayer(`/api/raster/tiles/satellite/{z}/{x}/{y}?date=${dateInput.value}`, {maxZoom: 9, attribution: "NASA EOSDIS GIBS"}), "satellite");
    if (wasActive) { activeBasemap = satelliteLayer; satelliteLayer.addTo(map).bringToBack(); }
    showSource("satellite"); persistPreferences();
  });

  const gravityButton = document.getElementById("gravity-inspector");
  const markerButton = document.getElementById("candidate-marker");
  const diameterInput = document.getElementById("candidate-diameter");
  const drawingMethod = document.getElementById("drawing-method"); drawingMethod.value = preferences.drawingMethod;
  const draftPanel = document.getElementById("candidate-draft");
  let gravityMode = false, candidateMode = false, draftMarker, draftCircle, dragStart, dragPreview, firstRim;
  function setGravityMode(enabled) {
    gravityMode = enabled; gravityButton.classList.toggle("active", enabled);
    gravityButton.textContent = enabled ? "Click the map to sample gravity" : "Inspect WGM2012 gravity at a point";
  }
  function setCandidateMode(enabled) {
    candidateMode = enabled; markerButton.classList.toggle("active", enabled);
    markerButton.textContent = enabled ? (preferences.drawingMethod === "center-radius" ? "Drag from centre to rim" : preferences.drawingMethod === "rim-to-rim" ? "Click the first rim point" : "Click the map to place candidate") : "Mark a candidate on the map";
    map.getContainer().style.cursor = enabled || gravityMode ? "crosshair" : "";
  }
  function drawCandidateDraft() {
    if (!candidateDraft) return;
    const latlng = L.latLng(candidateDraft.latitude, candidateDraft.longitude);
    if (!draftMarker) {
      draftMarker = L.marker(latlng, {draggable: true}).addTo(map).on("dragend", event => {
        const point = event.target.getLatLng(); candidateDraft.latitude = point.lat; candidateDraft.longitude = point.lng; drawCandidateDraft(); persistPreferences();
      });
    } else draftMarker.setLatLng(latlng);
    if (draftCircle) draftCircle.remove();
    draftCircle = L.circle(latlng, {radius: candidateDraft.diameterKm * 500, color: "#55d6be", fillOpacity: .12, dashArray: "6 4"}).addTo(map);
    diameterInput.value = candidateDraft.diameterKm;
    document.getElementById("candidate-centre").textContent = `${candidateDraft.latitude.toFixed(5)}, ${candidateDraft.longitude.toFixed(5)}`;
    draftPanel.hidden = false;
  }
  function clearCandidateDraft() {
    candidateDraft = null; if (draftMarker) map.removeLayer(draftMarker); if (draftCircle) map.removeLayer(draftCircle);
    draftMarker = draftCircle = null; draftPanel.hidden = true; setCandidateMode(false); persistPreferences();
  }
  gravityButton.addEventListener("click", () => { setCandidateMode(false); setGravityMode(!gravityMode); map.getContainer().style.cursor = gravityMode ? "crosshair" : ""; });
  markerButton.addEventListener("click", () => { setGravityMode(false); setCandidateMode(!candidateMode); });
  drawingMethod.addEventListener("change", () => { preferences.drawingMethod = drawingMethod.value; firstRim = null; setCandidateMode(false); persistPreferences(); });
  diameterInput.addEventListener("input", () => {
    if (!candidateDraft) return; const value = Number(diameterInput.value);
    if (value >= .1 && value <= 10000) { candidateDraft.diameterKm = value; drawCandidateDraft(); persistPreferences(); }
  });
  document.getElementById("clear-candidate").addEventListener("click", clearCandidateDraft);
  document.getElementById("review-candidate").addEventListener("click", () => {
    if (!candidateDraft) return;
    const source = sourceInfo[activeBasemapSlug] || ["Interactive atlas map", ""];
    const params = new URLSearchParams({
      latitude: candidateDraft.latitude.toFixed(6), longitude: candidateDraft.longitude.toFixed(6),
      diameter_km: candidateDraft.diameterKm, title: `Candidate near ${candidateDraft.latitude.toFixed(2)}, ${candidateDraft.longitude.toFixed(2)}`,
      source_title: source[0], source_uri: source[1]
    });
    window.location.assign(`/submit/?${params}`);
  });
  map.on("mousedown", event => {
    if (!candidateMode || preferences.drawingMethod !== "center-radius") return;
    dragStart = event.latlng; map.dragging.disable(); L.DomEvent.preventDefault(event.originalEvent);
  });
  map.on("mousemove", event => {
    if (!dragStart) return; const radius = map.distance(dragStart, event.latlng);
    if (dragPreview) map.removeLayer(dragPreview); dragPreview = L.circle(dragStart, {radius, color: "#55d6be", dashArray: "6 4", fillOpacity: .08}).addTo(map);
  });
  map.on("mouseup", event => {
    if (!dragStart) return; const radius = map.distance(dragStart, event.latlng); map.dragging.enable();
    if (dragPreview) map.removeLayer(dragPreview); dragPreview = null;
    if (radius >= 50) { candidateDraft = {latitude: dragStart.lat, longitude: dragStart.lng, diameterKm: radius / 500}; drawCandidateDraft(); setCandidateMode(false); persistPreferences(); }
    dragStart = null;
  });
  map.on("click", async event => {
    if (candidateMode) {
      if (preferences.drawingMethod === "center-radius") return;
      if (preferences.drawingMethod === "rim-to-rim") {
        if (!firstRim) { firstRim = event.latlng; markerButton.textContent = "Click the opposite rim point"; return; }
        const midpoint = L.latLng((firstRim.lat + event.latlng.lat) / 2, (firstRim.lng + event.latlng.lng) / 2), diameterKm = map.distance(firstRim, event.latlng) / 1000;
        candidateDraft = {latitude: midpoint.lat, longitude: midpoint.lng, diameterKm}; firstRim = null;
      } else candidateDraft = {latitude: event.latlng.lat, longitude: event.latlng.lng, diameterKm: Number(diameterInput.value) || 100};
      drawCandidateDraft(); setCandidateMode(false); persistPreferences(); return;
    }
    if (!gravityMode) return;
    status.textContent = "Sampling WGM2012 gravity…"; status.classList.remove("quiet");
    try {
      const response = await fetch(`/api/raster/gravity-sample?lon=${event.latlng.lng}&lat=${event.latlng.lat}`);
      if (!response.ok) throw new Error("Gravity service unavailable");
      const data = await response.json(), values = data.values_mgal;
      L.popup().setLatLng(event.latlng).setContent(`<div class="gravity-popup"><strong>WGM2012 gravity context</strong><span>Bouguer: ${values.bouguer == null ? "unavailable" : Number(values.bouguer).toFixed(2) + " mGal"}</span><span>Isostatic: ${values.isostatic == null ? "unavailable" : Number(values.isostatic).toFixed(2) + " mGal"}</span><small>${esc(data.interpretation)}</small><a href="${data.source_url}" target="_blank" rel="noopener">Open native gravity globe ↗</a></div>`).openOn(map);
      status.textContent = "Gravity sample ready"; setTimeout(() => status.classList.add("quiet"), 900);
    } catch (_error) { status.textContent = "WGM2012 gravity service is temporarily unavailable."; }
  });
  if (candidateDraft) drawCandidateDraft();
  resetCallbacks.push(() => {
    clearCandidateDraft();
    document.getElementById("raster-opacity").value = defaultPreferences.rasterOpacity;
    dateInput.value = yesterday;
    document.querySelector('[data-basemap="street"]').checked = true; chooseBasemap("street");
    document.querySelectorAll("[data-raster]").forEach(input => { input.checked = false; map.removeLayer(rasterLayers[input.dataset.raster]); });
    activeRasterSlugs.clear(); setGravityMode(false);
    preferences.scoreField = defaultPreferences.scoreField; preferences.palette = defaultPreferences.palette; preferences.drawingMethod = defaultPreferences.drawingMethod;
    scoreField.value = preferences.scoreField; paletteSelect.value = preferences.palette; drawingMethod.value = preferences.drawingMethod; restyleScientificLayers();
  });
}

document.getElementById("reset-map")?.addEventListener("click", async () => {
  suspendPersistence = true;
  map.setView(defaultPreferences.center, defaultPreferences.zoom);
  document.querySelectorAll("[data-layer]").forEach(input => {
    input.checked = defaultPreferences.layers.includes(input.dataset.layer);
    setLayer(input.dataset.layer, input.checked);
  });
  resetCallbacks.forEach(callback => callback());
  if (window.ASTROBLEME_PREFERENCE_URL) {
    const csrf = document.querySelector("#map-preference-token input")?.value;
    await fetch(window.ASTROBLEME_PREFERENCE_URL, {method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": csrf}, body: JSON.stringify({reset: true})});
  }
  preferences = {...defaultPreferences}; suspendPersistence = false;
  status.textContent = "Map reset to defaults"; status.classList.remove("quiet"); setTimeout(() => status.classList.add("quiet"), 1200);
});
suspendPersistence = false;
