const map = L.map("map", {worldCopyJump: true, zoomControl: false}).setView([5, 15], 2);
L.control.zoom({position: "bottomright"}).addTo(map);
const streetLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18, attribution: "© OpenStreetMap contributors"}).addTo(map);

const palette = {
  "study-candidates": {color: "#e6a94a", weight: 1.4, opacity: .7},
  "repaired-catalogue": {color: "#73c6b6", weight: 2, radius: 5},
  "african-structures": {color: "#f1e6c8", weight: 2, radius: 5},
  "negative-controls": {color: "#e36f5b", weight: 2, fillOpacity: .18},
  "active-faults": {color: "#9b6bc6", weight: .8, opacity: .55},
  community: {color: "#ff6f61", weight: 2.5, radius: 7}
};
const loaded = {}, groups = {};
const status = document.getElementById("map-status");

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
  try { const group = await loadLayer(slug); enabled ? group.addTo(map) : map.removeLayer(group); }
  catch (error) { status.textContent = error.message; status.classList.remove("quiet"); }
}
document.querySelectorAll("[data-layer]").forEach(input => {
  input.addEventListener("change", () => setLayer(input.dataset.layer, input.checked));
  if (input.checked) setLayer(input.dataset.layer, true);
});
document.getElementById("map-search").addEventListener("input", event => {
  const q = event.target.value.trim().toLowerCase(); if (q.length < 3) return;
  for (const group of Object.values(groups)) for (const layer of group.getLayers()) {
    if (layer._searchText?.includes(q)) { map.fitBounds(layer.getBounds ? layer.getBounds().pad(.6) : L.latLngBounds([layer.getLatLng()])); layer.openPopup(); return; }
  }
});

if (window.ASTROBLEME_RASTER_ACCESS) {
  const sourcePanel = document.getElementById("remote-source");
  const dateInput = document.getElementById("satellite-date");
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  dateInput.value = yesterday;
  dateInput.max = new Date().toISOString().slice(0, 10);

  const sourceInfo = {
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
  const activeRasters = new Set();
  let activeBasemap = streetLayer;

  function showSource(slug) {
    const info = sourceInfo[slug];
    if (info) sourcePanel.innerHTML = `<strong>${esc(info[0])}</strong><br><a href="${info[1]}" target="_blank" rel="noopener">Provider documentation ↗</a><br>Streamed through the atlas allowlist; no server-side raster cache.`;
  }
  function attachRasterErrors(layer, slug) {
    layer.on("tileerror", () => { status.textContent = `${sourceInfo[slug]?.[0] || slug} is temporarily unavailable.`; status.classList.remove("quiet"); });
    return layer;
  }
  attachRasterErrors(aerialLayer, "aerial"); attachRasterErrors(satelliteLayer, "satellite");
  Object.entries(rasterLayers).forEach(([slug, layer]) => attachRasterErrors(layer, slug));

  document.querySelectorAll("[data-basemap]").forEach(input => input.addEventListener("change", () => {
    if (!input.checked) return;
    map.removeLayer(activeBasemap);
    if (input.dataset.basemap === "aerial") activeBasemap = aerialLayer;
    else if (input.dataset.basemap === "satellite") activeBasemap = satelliteLayer;
    else activeBasemap = streetLayer;
    activeBasemap.addTo(map).bringToBack();
    if (input.dataset.basemap !== "street") showSource(input.dataset.basemap);
  }));

  document.querySelectorAll("[data-raster]").forEach(input => input.addEventListener("change", () => {
    const slug = input.dataset.raster, layer = rasterLayers[slug];
    if (input.checked) { layer.setOpacity(Number(document.getElementById("raster-opacity").value) / 100).addTo(map); activeRasters.add(slug); showSource(slug); }
    else { map.removeLayer(layer); activeRasters.delete(slug); }
  }));

  document.getElementById("raster-opacity").addEventListener("input", event => {
    const opacity = Number(event.target.value) / 100;
    activeRasters.forEach(slug => rasterLayers[slug].setOpacity(opacity));
  });

  dateInput.addEventListener("change", () => {
    const wasActive = map.hasLayer(satelliteLayer);
    if (wasActive) map.removeLayer(satelliteLayer);
    satelliteLayer = attachRasterErrors(L.tileLayer(`/api/raster/tiles/satellite/{z}/{x}/{y}?date=${dateInput.value}`, {maxZoom: 9, attribution: "NASA EOSDIS GIBS"}), "satellite");
    if (wasActive) { activeBasemap = satelliteLayer; satelliteLayer.addTo(map).bringToBack(); }
    showSource("satellite");
  });

  const gravityButton = document.getElementById("gravity-inspector");
  let gravityMode = false;
  gravityButton.addEventListener("click", () => {
    gravityMode = !gravityMode;
    gravityButton.classList.toggle("active", gravityMode);
    gravityButton.textContent = gravityMode ? "Click the map to sample gravity" : "Inspect WGM2012 gravity at a point";
    map.getContainer().style.cursor = gravityMode ? "crosshair" : "";
  });
  map.on("click", async event => {
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
}
