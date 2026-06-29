const defaultLayerStyles = {
  "study-candidates": {lineStyle: "dotted", lineWidth: 1.5},
  "repaired-catalogue": {lineStyle: "dotted", lineWidth: 1.5},
  "african-structures": {lineStyle: "dotted", lineWidth: 1.5},
  "negative-controls": {lineStyle: "solid", lineWidth: 1.5},
  "active-faults": {lineStyle: "solid", lineWidth: 1.5},
  "my-candidates": {lineStyle: "solid", lineWidth: 1.5},
  "other-candidates": {lineStyle: "dashed", lineWidth: 1.5},
  community: {lineStyle: "solid", lineWidth: 1.5}
};
const defaultPreferences = {
  center: [5, 15], zoom: 2, layers: ["study-candidates", "repaired-catalogue", "african-structures", "my-candidates"],
  basemap: "aerial", labels: true, rasters: [], rasterOpacity: 68, candidateDraft: null,
  scoreField: "followup_score", palette: "turbo", drawingMethod: "center-radius", detailMode: "popup", layerStyles: defaultLayerStyles
};
const savedPreferences = JSON.parse(document.getElementById("map-preferences")?.textContent || "{}");
let preferences = {...defaultPreferences, ...savedPreferences};
preferences.layerStyles = {...defaultLayerStyles, ...(savedPreferences.layerStyles || {})};
const syncedViewRequest = parseSyncedViewRequest();
if (syncedViewRequest) preferences = {...preferences, ...syncedViewRequest};
const sharedFeatureRequest = parseSharedFeatureRequest();
if (sharedFeatureRequest) {
  preferences = {...preferences, ...sharedFeatureRequest.preferences};
  if (window.ASTROBLEME_LAYER_URLS?.[sharedFeatureRequest.layer] && !preferences.layers.includes(sharedFeatureRequest.layer)) {
    preferences.layers = [...preferences.layers, sharedFeatureRequest.layer];
  }
}
const map = L.map("map", {worldCopyJump: true, zoomControl: false}).setView(preferences.center, preferences.zoom);
L.control.zoom({position: "bottomright"}).addTo(map);
L.control.scale({position: "bottomleft", metric: true, imperial: false, maxWidth: 160}).addTo(map);
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
const mapRegion = document.querySelector(".map-region");
const featureSidebar = document.getElementById("feature-sidebar");
const featureSidebarContent = document.getElementById("feature-sidebar-content");
const atlasShell = document.querySelector(".atlas-shell");
const resetCallbacks = [];
let saveTimer, suspendPersistence = true, activeBasemapSlug = "street", activeRasterSlugs = new Set(), labelsActive = preferences.labels !== false;
let candidateDraft = preferences.candidateDraft, activeFeatureLayer = null;
const scientificPalettes = {
  turbo: ["#30123b", "#4666e8", "#1bcfd4", "#65fe62", "#d6e935", "#f99217", "#7a0403"],
  viridis: ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
  plasma: ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"],
  inferno: ["#000004", "#420a68", "#932667", "#dd513a", "#fca50a", "#fcffa4"],
  magma: ["#000004", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"],
  cividis: ["#00204c", "#414d6b", "#7d7c78", "#b9ac70", "#ffea46"],
  rdbu: ["#67001f", "#d6604d", "#f7f7f7", "#4393c3", "#053061"]
};
const lineDashes = {solid: null, dashed: "7 5", dotted: "1 5"};
const centerMarkerLayers = new Set(["study-candidates", "my-candidates", "other-candidates", "community"]);

function esc(value) { const d = document.createElement("div"); d.textContent = value ?? "—"; return d.innerHTML; }
function csrfToken() { return document.querySelector("#map-preference-token input")?.value || ""; }
function parseSyncedViewRequest() {
  const params = new URLSearchParams(window.location.search);
  const lat = Number(params.get("lat")), lon = Number(params.get("lon")), zoom = Number(params.get("z"));
  const parsed = {};
  if (Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90) parsed.center = [lat, ((lon + 180) % 360) - 180];
  if (Number.isFinite(zoom)) parsed.zoom = Math.max(1, Math.min(18, Math.round(zoom)));
  const basemap = params.get("basemap");
  if (basemap) parsed.basemap = basemap;
  if (params.has("labels")) parsed.labels = params.get("labels") !== "0";
  if (params.has("rasters")) parsed.rasters = params.get("rasters").split(",").filter(Boolean);
  return Object.keys(parsed).length ? parsed : null;
}
function parseSharedFeatureRequest() {
  const params = new URLSearchParams(window.location.search);
  const layer = params.get("layer"), feature = params.get("feature");
  if (!layer || !feature) return null;
  const parsed = {layer, feature, preferences: {}};
  const basemap = params.get("basemap");
  if (basemap) parsed.preferences.basemap = basemap;
  if (params.has("labels")) parsed.preferences.labels = params.get("labels") !== "0";
  if (params.has("rasters")) parsed.preferences.rasters = params.get("rasters").split(",").filter(Boolean);
  if (params.has("rasterOpacity")) parsed.preferences.rasterOpacity = Number(params.get("rasterOpacity")) || preferences.rasterOpacity;
  if (params.has("scoreField")) parsed.preferences.scoreField = params.get("scoreField");
  if (params.has("palette")) parsed.preferences.palette = params.get("palette");
  if (params.has("detail")) parsed.preferences.detailMode = params.get("detail");
  return parsed;
}
function refreshMapSize() { setTimeout(() => map.invalidateSize(), 220); }
function centerMarkerIcon(selected = false) {
  return L.divIcon({className: `candidate-center-marker${selected ? " selected" : ""}`, html: "+", iconSize: [20, 20], iconAnchor: [10, 10]});
}
function layerAppearance(slug) {
  const base = palette[slug] || {};
  const saved = preferences.layerStyles?.[slug] || {};
  const lineStyle = lineDashes.hasOwnProperty(saved.lineStyle) ? saved.lineStyle : "solid";
  const lineWidth = Number.isFinite(Number(saved.lineWidth)) ? Math.max(1, Math.min(8, Number(saved.lineWidth))) : (base.weight || 2);
  return {lineStyle, lineWidth};
}
function styledLayerOptions(slug, colour) {
  const appearance = layerAppearance(slug);
  const dashArray = lineDashes[appearance.lineStyle];
  return {...(palette[slug] || {}), color: colour || palette[slug]?.color, weight: appearance.lineWidth, dashArray};
}
function selectedLayerOptions(layer) {
  const base = layer._baseStyle || styledLayerOptions(layer._layerSlug);
  return {...base, color: "#fff7a8", weight: Math.max((base.weight || 2) + 2.5, 4), opacity: 1, fillOpacity: base.fillOpacity ?? .22};
}
function setCenterMarkerSelected(layer, selected) {
  layer?._centerMarker?.setIcon(centerMarkerIcon(selected));
}
function clearFeatureSelection() {
  if (!activeFeatureLayer) return;
  if (activeFeatureLayer.setStyle) activeFeatureLayer.setStyle(activeFeatureLayer._baseStyle || styledLayerOptions(activeFeatureLayer._layerSlug));
  setCenterMarkerSelected(activeFeatureLayer, false);
  activeFeatureLayer = null;
}
function selectFeatureLayer(layer) {
  if (activeFeatureLayer && activeFeatureLayer !== layer) clearFeatureSelection();
  activeFeatureLayer = layer;
  if (layer?.setStyle) layer.setStyle(selectedLayerOptions(layer));
  setCenterMarkerSelected(layer, true);
  layer?.bringToFront?.();
  layer?._centerMarker?.bringToFront?.();
}
function layerCenter(layer) {
  if (layer.getLatLng) return layer.getLatLng();
  const bounds = layer.getBounds?.();
  return bounds?.isValid?.() ? bounds.getCenter() : null;
}
function addCandidateCenterMarker(slug, layer, group) {
  if (!centerMarkerLayers.has(slug)) return;
  const center = layerCenter(layer);
  if (!center) return;
  const marker = L.marker(center, {icon: centerMarkerIcon(false), keyboard: false, zIndexOffset: 300});
  marker.on("click", () => showFeatureDetail(layer));
  layer._centerMarker = marker;
  group.addLayer(marker);
}
function propsFor(feature) {
  const p = feature.properties || {};
  return {
    title: p.candidate_id || p.title || p.display_name || p.name || p.Name || "Map feature",
    score: p.followup_score ?? p.intake_score,
    scoreLabel: p.followup_score != null ? "Follow-up score" : p.intake_score != null ? "Intake score" : null,
    diameter: p.diameter_km ?? p.structure_diameter_km ?? p.diameter_max_km,
    status: p.review_tier || p.status || p.confirmed_raw || p.Type,
    note: p.score_interpretation || p.geometry_interpretation || p.Description || p.observed_feature,
    diagnosticSummary: p.diagnostic_summary,
    diagnosticFigureUrl: p.diagnostic_figure_url,
    diagnosticFigureTitle: p.diagnostic_figure_title || "Elevation analysis diagnostic",
    scoreBreakdown: Array.isArray(p.score_breakdown) ? p.score_breakdown : scoreBreakdownFromProperties(p),
    actions: p.actions || {},
    reviewStatus: p.review_status,
    searchable: JSON.stringify(p).toLowerCase()
  };
}
function scoreBreakdownFromProperties(p) {
  const fields = [
    ["followup_score", "Follow-up score"], ["data_quality", "Data quality"], ["topography_score_unweighted", "Topography"],
    ["radial_alignment", "Radial alignment"], ["hough_percentile", "Annular peak"], ["angular_continuity", "Angular continuity"],
    ["radius_match", "Radius match"], ["centre_match", "Centre match"], ["relief_score", "Relief"],
    ["geology_independence", "Geology independence"], ["gravity_consensus_percentile", "Gravity percentile"],
    ["magnetic_ring_score_stratified_percentile", "Magnetic percentile"]
  ];
  return fields.filter(([key]) => p[key] !== null && p[key] !== undefined && p[key] !== "").map(([key, label]) => ({key, label, value: p[key]}));
}
function metricLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return esc(value);
  if (Math.abs(number) >= 100) return number.toFixed(1);
  return number.toFixed(3);
}
function popupActions(p) {
  const actions = p.actions || {};
  const share = `<button class="popup-share-button" type="button">Copy share link</button>`;
  const edit = actions.edit_url ? `<a class="popup-action-button" href="${esc(actions.edit_url)}">Edit</a>` : "";
  const choices = Array.isArray(actions.status_choices) ? actions.status_choices : [];
  const status = actions.status_url ? `<form class="popup-status-form" data-status-url="${esc(actions.status_url)}"><label>Status<select name="status">${choices.map(choice => `<option value="${esc(choice.value)}" ${choice.value === p.reviewStatus ? "selected" : ""}>${esc(choice.label)}</option>`).join("")}</select></label><textarea name="note" rows="2" placeholder="Review note"></textarea><button type="submit">Save</button></form>` : "";
  const del = actions.delete_url ? `<button class="popup-delete-button" type="button" data-delete-url="${esc(actions.delete_url)}">Delete</button>` : "";
  return `<div class="popup-actions">${share}${edit}${status}${del}</div>`;
}
function featureDetail(feature, mode = "popup") {
  const p = propsFor(feature);
  const geophysicalKeys = new Set(["gravity_consensus_percentile", "magnetic_ring_score_stratified_percentile"]);
  const normalScores = p.scoreBreakdown.filter(item => !geophysicalKeys.has(item.key));
  const geophysicalScores = p.scoreBreakdown.filter(item => geophysicalKeys.has(item.key));
  const scoreItems = items => items.map(item => `<div><dt>${esc(item.label)}</dt><dd>${metricLabel(item.value)}</dd></div>`).join("");
  const breakdown = normalScores.length ? `<section class="popup-section"><h3>Screening metrics</h3><dl class="popup-breakdown">${scoreItems(normalScores)}</dl></section>` : "";
  const geophysics = geophysicalScores.length ? `<section class="popup-section popup-geophysics"><h3>Geophysical context</h3><dl class="popup-breakdown">${scoreItems(geophysicalScores)}</dl></section>` : "";
  const figure = p.diagnosticFigureUrl ? `<figure class="popup-diagnostic"><img src="${esc(p.diagnosticFigureUrl)}" alt="${esc(p.diagnosticFigureTitle)} for ${esc(p.title)}" loading="lazy"><figcaption>${esc(p.diagnosticFigureTitle)}</figcaption></figure>` : "";
  const summary = p.diagnosticSummary ? `<p>${esc(p.diagnosticSummary)}</p>` : "";
  const score = p.scoreLabel && Number.isFinite(Number(p.score)) ? `<div><dt>${esc(p.scoreLabel)}</dt><dd>${Number(p.score).toFixed(3)}</dd></div>` : "";
  const diameter = p.diameter ? `<div><dt>Diameter</dt><dd>${Number(p.diameter).toFixed(1)} km</dd></div>` : "";
  const reviewStatus = p.status ? `<div><dt>Status/tier</dt><dd>${esc(p.status)}</dd></div>` : "";
  const meta = score || diameter || reviewStatus ? `<dl class="feature-meta">${score}${diameter}${reviewStatus}</dl>` : "";
  const notes = p.note || summary ? `<section class="feature-summary">${p.note ? `<p>${esc(p.note)}</p>` : ""}${summary}</section>` : "";
  const contentClass = figure ? "feature-detail-body has-diagnostic" : "feature-detail-body";
  return `<article class="map-popup feature-detail feature-detail-${mode}"><header><strong>${esc(p.title)}</strong>${meta}</header>${notes}<div class="${contentClass}"><div>${breakdown}${geophysics}</div>${figure}</div>${popupActions(p)}</article>`;
}
function popup(feature) {
  return featureDetail(feature, "popup");
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
    const colour = Number.isFinite(raw) && values.length ? paletteColour(max === min ? .5 : (raw - min) / (max - min)) : palette[slug]?.color;
    layer._baseStyle = {...styledLayerOptions(slug, colour), fillOpacity: palette[slug]?.fillOpacity ?? .22};
    layer.setStyle(layer === activeFeatureLayer ? selectedLayerOptions(layer) : layer._baseStyle);
  }));
  const legend = document.getElementById("score-legend");
  const fieldLabel = document.querySelector(`#score-field option[value="${preferences.scoreField}"]`)?.textContent || preferences.scoreField;
  const digits = preferences.scoreField === "diameter_km" ? 1 : 3;
  if (legend) legend.innerHTML = values.length ? `<strong>${esc(fieldLabel)}</strong><span>${esc(min.toFixed(digits))}</span><i style="background:linear-gradient(90deg,${scientificPalettes[preferences.palette].join(",")})"></i><span>${esc(max.toFixed(digits))}</span><small>${values.length.toLocaleString()} displayed values · exact data range</small>` : `<strong>${esc(fieldLabel)}</strong><small>No numeric values in displayed layers</small>`;
}
function closeFeatureSidebar() {
  if (featureSidebar) featureSidebar.hidden = true;
  mapRegion?.classList.remove("sidebar-open");
}
function bindFeatureActions(root, layer, sourceMode = "popup") {
  if (!root || !layer) return;
  root.querySelector(".popup-share-button")?.addEventListener("click", async () => {
    const shareUrl = featureShareUrl(layer);
    try {
      await navigator.clipboard.writeText(shareUrl);
      status.textContent = "Share link copied"; status.classList.remove("quiet"); setTimeout(() => status.classList.add("quiet"), 1200);
    } catch (_error) {
      window.prompt("Copy share link", shareUrl);
    }
  });
  root.querySelector(".popup-status-form")?.addEventListener("submit", async formEvent => {
    formEvent.preventDefault();
    const form = formEvent.currentTarget;
    try {
      const response = await fetch(form.dataset.statusUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken(), "Accept": "application/json"},
        body: JSON.stringify({status: form.elements.status.value, note: form.elements.note.value})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Status update failed");
      layer.feature.properties = data.properties;
      layer.setPopupContent?.(popup(layer.feature));
      if (sourceMode === "sidebar") openFeatureSidebar(layer);
      else { map.closePopup(); openFeaturePopup(layer); }
      restyleScientificLayers();
      status.textContent = "Candidate status updated"; status.classList.remove("quiet"); setTimeout(() => status.classList.add("quiet"), 900);
    } catch (error) { status.textContent = error.message; status.classList.remove("quiet"); }
  });
  root.querySelector(".popup-delete-button")?.addEventListener("click", async buttonEvent => {
    const button = buttonEvent.currentTarget;
    if (!confirm("Delete this candidate?")) return;
    try {
      const response = await fetch(button.dataset.deleteUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken(), "Accept": "application/json"},
        body: "{}"
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Delete failed");
      map.closePopup(); closeFeatureSidebar(); clearFeatureSelection(); removeFeatureLayer(layer);
      status.textContent = "Candidate deleted"; status.classList.remove("quiet"); setTimeout(() => status.classList.add("quiet"), 900);
    } catch (error) { status.textContent = error.message; status.classList.remove("quiet"); }
  });
}
function featureShareId(layer) {
  const feature = layer?.feature || {};
  const properties = feature.properties || {};
  return properties.candidate_id || properties.candidate_uuid || feature.id || properties.title || "";
}
function featureShareUrl(layer) {
  const params = new URLSearchParams();
  params.set("layer", layer?._layerSlug || "study-candidates");
  params.set("feature", featureShareId(layer));
  params.set("basemap", activeBasemapSlug);
  params.set("labels", labelsActive ? "1" : "0");
  if (activeRasterSlugs.size) params.set("rasters", [...activeRasterSlugs].join(","));
  params.set("rasterOpacity", String(Number(document.getElementById("raster-opacity")?.value || preferences.rasterOpacity || 68)));
  params.set("scoreField", preferences.scoreField);
  params.set("palette", preferences.palette);
  params.set("detail", preferences.detailMode);
  return `${window.location.origin}${window.location.pathname}?${params}`;
}
function featureMatchesShare(layer, request) {
  const feature = layer?.feature;
  if (!feature) return false;
  const properties = feature.properties || {};
  return [feature.id, properties.candidate_id, properties.candidate_uuid, properties.title, properties.name].filter(Boolean).some(value => String(value) === request.feature);
}
function fitSharedFeature(layer) {
  const properties = layer.feature?.properties || {};
  const bounds = layer.getBounds?.();
  if (bounds?.isValid?.()) {
    map.fitBounds(bounds.pad(.65), {maxZoom: 9});
    return;
  }
  const center = layerCenter(layer);
  if (!center) return;
  const diameter = Number(properties.diameter_km || properties.structure_diameter_km || 0);
  if (diameter > 0) map.fitBounds(L.circle(center, {radius: diameter * 650}).getBounds(), {maxZoom: 9});
  else map.setView(center, Math.max(map.getZoom(), 8));
}
async function initializeSharedFeature() {
  if (!sharedFeatureRequest || !window.ASTROBLEME_LAYER_URLS?.[sharedFeatureRequest.layer]) return;
  const input = document.querySelector(`[data-layer="${sharedFeatureRequest.layer}"]`);
  if (input) input.checked = true;
  const group = await loadLayer(sharedFeatureRequest.layer);
  group.addTo(map);
  restyleScientificLayers();
  const layer = group.getLayers().find(candidate => featureMatchesShare(candidate, sharedFeatureRequest));
  if (!layer) {
    status.textContent = "Shared feature was not found in the visible atlas layers.";
    status.classList.remove("quiet");
    return;
  }
  fitSharedFeature(layer);
  showFeatureDetail(layer);
  status.textContent = "Shared candidate loaded";
  status.classList.remove("quiet");
  setTimeout(() => status.classList.add("quiet"), 1200);
}
function openFeaturePopup(layer) {
  closeFeatureSidebar();
  selectFeatureLayer(layer);
  layer.bindPopup(popup(layer.feature), {className: "feature-popup", maxWidth: 760, minWidth: 380, autoPanPadding: [24, 24]}).openPopup();
}
function openFeatureSidebar(layer) {
  if (!featureSidebar || !featureSidebarContent) return openFeaturePopup(layer);
  selectFeatureLayer(layer);
  map.closePopup();
  featureSidebarContent.innerHTML = featureDetail(layer.feature, "sidebar");
  featureSidebar.hidden = false;
  mapRegion?.classList.add("sidebar-open");
  bindFeatureActions(featureSidebarContent, layer, "sidebar");
}
function showFeatureDetail(layer) {
  if (preferences.detailMode === "sidebar") openFeatureSidebar(layer);
  else openFeaturePopup(layer);
}
async function loadLayer(slug) {
  if (loaded[slug]) return groups[slug];
  status.textContent = `Loading ${slug.replaceAll("-", " ")}…`;
  const response = await fetch(window.ASTROBLEME_LAYER_URLS[slug]);
  if (!response.ok) throw new Error(`Layer failed: ${slug}`);
  const data = await response.json();
  const style = styledLayerOptions(slug);
  const group = L.featureGroup();
  const geoJson = L.geoJSON(data, {
    style: () => styledLayerOptions(slug),
    pointToLayer: (_feature, latlng) => L.circleMarker(latlng, style),
    onEachFeature: (feature, layer) => {
      layer._layerSlug = slug;
      layer._baseStyle = styledLayerOptions(slug);
      layer._searchText = propsFor(feature).searchable;
      layer.on("click", () => showFeatureDetail(layer));
    }
  });
  geoJson.eachLayer(layer => {
    group.addLayer(layer);
    addCandidateCenterMarker(slug, layer, group);
  });
  loaded[slug] = true; groups[slug] = group;
  document.querySelector(`[data-count="${slug}"]`).textContent = `${data.features.length.toLocaleString()} features`;
  status.textContent = "Ready"; setTimeout(() => status.classList.add("quiet"), 900);
  return group;
}
async function setLayer(slug, enabled) {
  try {
    const group = await loadLayer(slug);
    if (!enabled && activeFeatureLayer && group.hasLayer?.(activeFeatureLayer)) {
      map.closePopup();
      closeFeatureSidebar();
      clearFeatureSelection();
    }
    enabled ? group.addTo(map) : map.removeLayer(group);
    restyleScientificLayers();
  }
  catch (error) { status.textContent = error.message; status.classList.remove("quiet"); }
}
function currentPreferences() {
  const center = map.getCenter();
  return {
    center: [center.lat, center.lng], zoom: map.getZoom(),
    layers: Array.from(document.querySelectorAll("[data-layer]:checked"), input => input.dataset.layer),
    basemap: activeBasemapSlug, labels: labelsActive, rasters: [...activeRasterSlugs],
    rasterOpacity: Number(document.getElementById("raster-opacity")?.value || 68),
    candidateDraft, scoreField: preferences.scoreField, palette: preferences.palette, drawingMethod: preferences.drawingMethod, detailMode: preferences.detailMode,
    layerStyles: preferences.layerStyles || {}
  };
}
function setSyncedLink(target, url, params) {
  const link = document.querySelectorAll(`[data-view-sync="${target}"]`);
  link.forEach(item => {
    const next = new URL(url, window.location.origin);
    Object.entries(params).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") next.searchParams.set(key, String(value));
    });
    item.href = `${next.pathname}${next.search}`;
  });
}
function updateViewSyncLinks() {
  const current = currentPreferences();
  const params = {
    lat: current.center[0].toFixed(5),
    lon: current.center[1].toFixed(5),
    z: current.zoom,
    basemap: current.basemap,
    labels: current.labels ? "1" : "0",
    rasters: current.rasters.join(","),
  };
  setSyncedLink("globe", "/globe/", params);
  setSyncedLink("atlas", "/", params);
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

document.getElementById("toggle-atlas-panel")?.addEventListener("click", event => {
  const button = event.currentTarget;
  const collapsed = !atlasShell?.classList.contains("sidebar-collapsed");
  atlasShell?.classList.toggle("sidebar-collapsed", collapsed);
  button.setAttribute("aria-pressed", String(collapsed));
  button.setAttribute("aria-label", collapsed ? "Show layer sidebar" : "Hide layer sidebar");
  refreshMapSize();
});
document.getElementById("fullscreen-map")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await (mapRegion || document.documentElement).requestFullscreen();
  } catch (_error) {
    status.textContent = "Fullscreen is not available in this browser.";
    status.classList.remove("quiet");
  }
  button.setAttribute("aria-label", document.fullscreenElement ? "Exit fullscreen" : "Enter fullscreen");
  refreshMapSize();
});
document.addEventListener("fullscreenchange", () => {
  const button = document.getElementById("fullscreen-map");
  button?.setAttribute("aria-label", document.fullscreenElement ? "Exit fullscreen" : "Enter fullscreen");
  refreshMapSize();
});

document.querySelectorAll("[data-layer]").forEach(input => {
  input.checked = preferences.layers.includes(input.dataset.layer);
  input.addEventListener("change", () => { setLayer(input.dataset.layer, input.checked); persistPreferences(); });
  if (input.checked) setLayer(input.dataset.layer, true);
});
map.on("moveend", persistPreferences);
map.on("moveend", updateViewSyncLinks);
document.getElementById("map-search").addEventListener("input", event => {
  const q = event.target.value.trim().toLowerCase(); if (q.length < 3) return;
  for (const group of Object.values(groups)) for (const layer of group.getLayers()) {
    if (layer._searchText?.includes(q)) { map.fitBounds(layer.getBounds ? layer.getBounds().pad(.6) : L.latLngBounds([layer.getLatLng()])); showFeatureDetail(layer); return; }
  }
});
const scoreField = document.getElementById("score-field"), paletteSelect = document.getElementById("map-palette");
if (scoreField) { scoreField.value = preferences.scoreField; scoreField.addEventListener("change", () => { preferences.scoreField = scoreField.value; restyleScientificLayers(); persistPreferences(); }); }
if (paletteSelect) { paletteSelect.value = preferences.palette; paletteSelect.addEventListener("change", () => { preferences.palette = paletteSelect.value; restyleScientificLayers(); persistPreferences(); }); }
document.getElementById("feature-sidebar-close")?.addEventListener("click", () => { closeFeatureSidebar(); clearFeatureSelection(); });
document.querySelectorAll("[data-detail-mode]").forEach(input => {
  input.checked = input.dataset.detailMode === preferences.detailMode;
  input.addEventListener("change", () => {
    if (!input.checked) return;
    preferences.detailMode = input.dataset.detailMode;
    if (preferences.detailMode === "popup") { closeFeatureSidebar(); clearFeatureSelection(); }
    else map.closePopup();
    persistPreferences();
  });
});
document.querySelectorAll("[data-layer-line-style]").forEach(select => {
  const slug = select.dataset.layerLineStyle, current = layerAppearance(slug);
  select.value = current.lineStyle;
  select.addEventListener("change", () => {
    preferences.layerStyles = {...(preferences.layerStyles || {}), [slug]: {...layerAppearance(slug), lineStyle: select.value}};
    restyleScientificLayers(); persistPreferences();
  });
});
document.querySelectorAll("[data-layer-line-width]").forEach(input => {
  const slug = input.dataset.layerLineWidth, current = layerAppearance(slug);
  input.value = current.lineWidth;
  input.addEventListener("input", () => {
    const value = Math.max(1, Math.min(8, Number(input.value) || current.lineWidth));
    preferences.layerStyles = {...(preferences.layerStyles || {}), [slug]: {...layerAppearance(slug), lineWidth: value}};
    restyleScientificLayers(); persistPreferences();
  });
});

function removeFeatureLayer(layer) {
  Object.values(groups).forEach(group => {
    if (group.hasLayer?.(layer)) group.removeLayer(layer);
    if (layer._centerMarker && group.hasLayer?.(layer._centerMarker)) group.removeLayer(layer._centerMarker);
  });
  restyleScientificLayers();
}
map.on("popupopen", event => bindFeatureActions(event.popup.getElement(), event.popup._source, "popup"));
map.on("popupclose", event => {
  if (preferences.detailMode !== "sidebar" && event.popup._source === activeFeatureLayer) clearFeatureSelection();
});

const analysisStatusPanel = document.getElementById("analysis-status-panel");
function numberLabel(value, digits = 0) {
  return value === null || value === undefined || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits);
}
function statusClass(value) {
  return String(value || "").replace(/_/g, "-");
}
function renderAnalysisStatus(data) {
  if (!analysisStatusPanel) return;
  const totals = data.totals || {}, followup = data.followup || {}, jobs = data.jobs || {}, runs = data.runs || {};
  const recent = Array.isArray(data.recent) ? data.recent : [];
  const active = (jobs.queued || 0) + (jobs.claimed || 0) + (jobs.running || 0);
  const attention = (followup.failed || 0) + (followup.source_unavailable || 0) + (jobs.failed || 0);
  const progress = Math.max(0, Math.min(100, Number(totals.progress_percent || 0)));
  const recentHtml = recent.length ? recent.map(item => {
    const score = item.score === null || item.score === undefined ? "" : `<span>Score ${numberLabel(item.score, 3)}</span>`;
    const percentile = item.score_percentile === null || item.score_percentile === undefined ? "" : `<span>Pctl ${numberLabel(item.score_percentile, 1)}</span>`;
    const quality = item.data_quality === null || item.data_quality === undefined ? "" : `<span>Quality ${numberLabel(item.data_quality, 2)}</span>`;
    const summary = item.summary ? `<small>${esc(item.summary)}</small>` : "";
    return `<article class="analysis-item analysis-${statusClass(item.state)}"><strong>${esc(item.title)}</strong><div><span>${esc(item.state_label)}</span>${score}${percentile}${quality}</div>${summary}</article>`;
  }).join("") : `<div class="analysis-empty">No submitted candidates yet.</div>`;
  const staff = data.staff_queue ? `<div class="analysis-staff"><strong>All worker jobs</strong><span>${Number(data.staff_queue.queued || 0).toLocaleString()} queued</span><span>${Number(data.staff_queue.running || 0).toLocaleString()} running</span><span>${Number(data.staff_queue.failed || 0).toLocaleString()} failed</span></div>` : "";
  analysisStatusPanel.innerHTML = `
    <div class="analysis-progress-row">
      <div><strong>${progress}%</strong><span>${Number(totals.finished || 0).toLocaleString()} of ${Number(totals.baseline_passed || 0).toLocaleString()} complete</span></div>
      <div class="analysis-progress" aria-label="Analysis progress"><i style="width:${progress}%"></i></div>
    </div>
    <div class="analysis-metrics">
      <div><strong>${Number(active).toLocaleString()}</strong><span>Active</span></div>
      <div><strong>${Number(followup.scored || 0).toLocaleString()}</strong><span>Scored</span></div>
      <div><strong>${Number(attention).toLocaleString()}</strong><span>Attention</span></div>
    </div>
    <div class="analysis-breakdown"><span>${Number(jobs.queued || 0).toLocaleString()} queued</span><span>${Number(jobs.claimed || 0).toLocaleString()} claimed</span><span>${Number(jobs.running || 0).toLocaleString()} running</span><span>${Number(runs.succeeded || 0).toLocaleString()} runs ok</span></div>
    ${staff}
    <div class="analysis-list">${recentHtml}</div>
    <div class="analysis-updated">Updated ${new Date(data.updated_at || Date.now()).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}</div>`;
}
async function refreshAnalysisStatus() {
  if (!analysisStatusPanel || !window.ASTROBLEME_ANALYSIS_STATUS_URL) return;
  try {
    const response = await fetch(window.ASTROBLEME_ANALYSIS_STATUS_URL, {headers: {"Accept": "application/json"}});
    if (!response.ok) throw new Error("Analysis status unavailable");
    renderAnalysisStatus(await response.json());
  } catch (_error) {
    analysisStatusPanel.innerHTML = `<div class="analysis-empty">Analysis status is temporarily unavailable.</div>`;
  }
}
refreshAnalysisStatus();
if (analysisStatusPanel) setInterval(refreshAnalysisStatus, 15000);

if (document.getElementById("remote-source")) {
  const sourcePanel = document.getElementById("remote-source");
  const labelOverlayInput = document.getElementById("label-overlay");
  const opacityInput = document.getElementById("raster-opacity");
  if (opacityInput) opacityInput.value = preferences.rasterOpacity;

  const sourceInfo = {
    street: ["OpenStreetMap", "https://www.openstreetmap.org/copyright"],
    aerial: ["Esri World Imagery", "https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9"],
    dark: ["CARTO Dark Matter basemap", "https://carto.com/basemaps/"],
    labels: ["CARTO labels and roads overlay", "https://carto.com/basemaps/"],
    gmrt: ["GMRT global multi-resolution topography", "https://www.gmrt.org/services/index.php"],
    "gmrt-masked": ["GMRT global multi-resolution topography (masked)", "https://www.gmrt.org/services/index.php"],
    "gebco-elevation": ["GEBCO latest elevation/bathymetry", "https://www.gebco.net/data-products/gebco-web-services/web-map-service"],
    "gebco-tid": ["GEBCO Type Identifier grid", "https://www.gebco.net/data-products/gebco-web-services/web-map-service"],
    magnetic: ["NOAA NCEI EMAG2v3", "https://www.ncei.noaa.gov/products/earth-magnetic-model-anomaly-grid-2"]
  };
  function truncateText(value, limit) {
    const text = String(value || "");
    return text.length > limit ? `${text.slice(0, Math.max(0, limit - 3))}...` : text;
  }
  function selectedSubmissionSource() {
    const basemap = sourceInfo[activeBasemapSlug] || sourceInfo.aerial;
    const overlays = [...activeRasterSlugs].map(slug => sourceInfo[slug]).filter(Boolean);
    const overlayNames = overlays.map(item => item[0]);
    const title = truncateText([basemap[0], ...overlayNames].join(" + "), 240);
    const resolutionParts = [`Basemap: ${basemap[0]}`];
    if (overlayNames.length) resolutionParts.push(`Study overlays: ${overlayNames.join(", ")}`);
    else resolutionParts.push("Study overlays: none selected");
    return {
      title,
      uri: basemap[1],
      resolution: truncateText(resolutionParts.join("; "), 120)
    };
  }
  const aerialLayer = L.tileLayer("/api/raster/tiles/aerial/{z}/{x}/{y}", {maxZoom: 18, attribution: "Esri, Maxar, Earthstar Geographics and contributors"});
  const darkLayer = L.tileLayer("/api/raster/tiles/dark/{z}/{x}/{y}", {maxZoom: 18, attribution: "© OpenStreetMap contributors, © CARTO"});
  const labelsLayer = L.tileLayer("/api/raster/tiles/labels/{z}/{x}/{y}", {maxZoom: 18, attribution: "© OpenStreetMap contributors, © CARTO"});
  const gmrtLayer = L.tileLayer.wms("/api/raster/wms/gmrt", {layers: "topo", format: "image/png", transparent: false, version: "1.1.1", attribution: "GMRT, Lamont-Doherty Earth Observatory, Columbia University"});
  const gmrtMaskedLayer = L.tileLayer.wms("/api/raster/wms/gmrt-masked", {layers: "topo-mask", format: "image/png", transparent: false, version: "1.1.1", attribution: "GMRT, Lamont-Doherty Earth Observatory, Columbia University"});
  const rasterLayers = {
    "gebco-elevation": L.tileLayer.wms("/api/raster/wms/gebco-elevation", {layers: "gebco_latest", format: "image/png", transparent: true, version: "1.1.1", attribution: "GEBCO Compilation Group"}),
    "gebco-tid": L.tileLayer.wms("/api/raster/wms/gebco-tid", {layers: "gebco_latest_tid", format: "image/png", transparent: true, version: "1.1.1", attribution: "GEBCO Compilation Group"}),
    magnetic: L.tileLayer("/api/raster/tiles/magnetic/{z}/{x}/{y}", {maxZoom: 8, attribution: "NOAA NCEI"})
  };
  const basemapLayers = {street: streetLayer, aerial: aerialLayer, dark: darkLayer, gmrt: gmrtLayer, "gmrt-masked": gmrtMaskedLayer};
  if (!basemapLayers[preferences.basemap]) preferences.basemap = defaultPreferences.basemap;
  let activeBasemap = streetLayer;

  const basemapSlugs = new Set(Object.keys(basemapLayers));
  function showSource(slug) {
    const info = sourceInfo[slug];
    if (info) {
      const prefix = basemapSlugs.has(slug) ? "Current basemap" : "Current layer";
      sourcePanel.innerHTML = `<strong>${prefix}: ${esc(info[0])}</strong><br><a href="${info[1]}" target="_blank" rel="noopener">Provider documentation ↗</a><br>${labelsActive && basemapSlugs.has(slug) ? "Labels/roads overlay enabled. " : ""}Streamed through the atlas allowlist; no server-side raster cache.`;
    }
  }
  function attachRasterErrors(layer, slug) {
    layer.on("tileerror", () => { status.textContent = `${sourceInfo[slug]?.[0] || slug} is temporarily unavailable.`; status.classList.remove("quiet"); });
    return layer;
  }
  function chooseBasemap(slug) {
    map.removeLayer(activeBasemap);
    activeBasemapSlug = basemapLayers[slug] ? slug : defaultPreferences.basemap;
    activeBasemap = basemapLayers[activeBasemapSlug];
    activeBasemap.addTo(map).bringToBack();
    map.getContainer().classList.toggle("dark-basemap", activeBasemapSlug === "dark");
    updateLabelOverlay();
    restyleScientificLayers();
    showSource(activeBasemapSlug);
    updateViewSyncLinks();
  }
  function updateLabelOverlay() {
    if (labelsActive && activeBasemapSlug !== "street") {
      labelsLayer.addTo(map);
      labelsLayer.bringToFront();
      Object.values(groups).forEach(group => group.bringToFront?.());
    } else map.removeLayer(labelsLayer);
  }
  attachRasterErrors(aerialLayer, "aerial"); attachRasterErrors(darkLayer, "dark"); attachRasterErrors(labelsLayer, "labels"); attachRasterErrors(gmrtLayer, "gmrt"); attachRasterErrors(gmrtMaskedLayer, "gmrt-masked");
  Object.entries(rasterLayers).forEach(([slug, layer]) => attachRasterErrors(layer, slug));
  if (labelOverlayInput) {
    labelOverlayInput.checked = labelsActive;
    labelOverlayInput.addEventListener("change", () => { labelsActive = labelOverlayInput.checked; updateLabelOverlay(); showSource(activeBasemapSlug); updateViewSyncLinks(); persistPreferences(); });
  }

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
      if (input.checked) { layer.setOpacity(Number(document.getElementById("raster-opacity").value) / 100).addTo(map); activeRasterSlugs.add(slug); layer.bringToFront?.(); Object.values(groups).forEach(group => group.bringToFront?.()); showSource(slug); }
      else { map.removeLayer(layer); activeRasterSlugs.delete(slug); }
      updateViewSyncLinks();
      persistPreferences();
    });
  });
  opacityInput?.addEventListener("input", event => {
    const opacity = Number(event.target.value) / 100;
    activeRasterSlugs.forEach(slug => rasterLayers[slug].setOpacity(opacity)); persistPreferences();
    updateViewSyncLinks();
  });
  if (window.ASTROBLEME_RASTER_ACCESS) {
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
      draftMarker = L.marker(latlng, {draggable: true, icon: centerMarkerIcon(true)}).addTo(map).on("dragend", event => {
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
    const source = selectedSubmissionSource();
    const params = new URLSearchParams({
      latitude: candidateDraft.latitude.toFixed(6), longitude: candidateDraft.longitude.toFixed(6),
      diameter_km: candidateDraft.diameterKm, title: `Candidate near ${candidateDraft.latitude.toFixed(2)}, ${candidateDraft.longitude.toFixed(2)}`,
      source_title: source.title, source_uri: source.uri, source_resolution: source.resolution
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
    opacityInput.value = defaultPreferences.rasterOpacity;
    labelsActive = defaultPreferences.labels; labelOverlayInput.checked = labelsActive;
    document.querySelector(`[data-basemap="${defaultPreferences.basemap}"]`).checked = true; chooseBasemap(defaultPreferences.basemap);
    document.querySelectorAll("[data-raster]").forEach(input => { input.checked = false; map.removeLayer(rasterLayers[input.dataset.raster]); });
    activeRasterSlugs.clear(); setGravityMode(false);
    preferences.scoreField = defaultPreferences.scoreField; preferences.palette = defaultPreferences.palette; preferences.drawingMethod = defaultPreferences.drawingMethod; preferences.detailMode = defaultPreferences.detailMode; preferences.layerStyles = {...defaultLayerStyles};
    scoreField.value = preferences.scoreField; paletteSelect.value = preferences.palette; drawingMethod.value = preferences.drawingMethod; restyleScientificLayers();
    document.querySelectorAll("[data-detail-mode]").forEach(input => { input.checked = input.dataset.detailMode === preferences.detailMode; });
    document.querySelectorAll("[data-layer-line-style]").forEach(select => { select.value = layerAppearance(select.dataset.layerLineStyle).lineStyle; });
    document.querySelectorAll("[data-layer-line-width]").forEach(input => { input.value = layerAppearance(input.dataset.layerLineWidth).lineWidth; });
    closeFeatureSidebar();
  });
  }
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
  preferences = {...defaultPreferences, layerStyles: {...defaultLayerStyles}}; suspendPersistence = false;
  status.textContent = "Map reset to defaults"; status.classList.remove("quiet"); setTimeout(() => status.classList.add("quiet"), 1200);
});
initializeSharedFeature().finally(() => { updateViewSyncLinks(); suspendPersistence = false; });
