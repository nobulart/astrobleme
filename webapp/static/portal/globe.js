;(async () => {
const token = JSON.parse(document.getElementById("cesium-ion-token").textContent || '""');
if (token) Cesium.Ion.defaultAccessToken = token;
const viewer = new Cesium.Viewer("cesium-globe", {baseLayer: false, baseLayerPicker: false, geocoder: false, animation: false, timeline: false, terrainProvider: new Cesium.EllipsoidTerrainProvider()});
const initialView = parseViewParams();
function parseViewParams() {
  const params = new URLSearchParams(window.location.search);
  const lat = Number(params.get("lat")), lon = Number(params.get("lon")), zoom = Number(params.get("z"));
  return {
    lat: Number.isFinite(lat) && lat >= -90 && lat <= 90 ? lat : 5,
    lon: Number.isFinite(lon) ? ((lon + 180) % 360) - 180 : 15,
    zoom: Number.isFinite(zoom) ? Math.max(1, Math.min(18, zoom)) : 2,
    basemap: params.get("basemap") || "aerial",
    labels: params.get("labels") !== "0",
  };
}
function cameraGeometry() {
  const canvas = viewer.scene.canvas;
  const width = canvas.clientWidth || 1280;
  const height = canvas.clientHeight || 720;
  const aspect = width / height;
  const fovy = viewer.camera.frustum.fovy || Cesium.Math.toRadians(60);
  return {aspect, fovy, width};
}
function zoomToHeight(zoom) {
  const {aspect, fovy, width} = cameraGeometry();
  const atlasWidth = 40075016 * width / (256 * Math.pow(2, Math.max(1, Math.min(18, zoom))));
  return Math.max(2500, atlasWidth / (2 * Math.tan(fovy / 2) * aspect));
}
function heightToZoom(height) {
  const {aspect, fovy, width} = cameraGeometry();
  const visibleWidth = Math.max(2500, height) * 2 * Math.tan(fovy / 2) * aspect;
  const zoom = Math.log2(40075016 * width / (256 * visibleWidth));
  return Math.max(1, Math.min(18, Math.round(zoom)));
}
function cameraCenter() {
  const canvas = viewer.scene.canvas;
  const windowCenter = new Cesium.Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2);
  let cartesian = viewer.camera.pickEllipsoid(windowCenter, viewer.scene.globe.ellipsoid);
  if (!cartesian) cartesian = viewer.camera.positionWC;
  const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
  return {
    lat: Cesium.Math.toDegrees(cartographic.latitude),
    lon: Cesium.Math.toDegrees(cartographic.longitude),
    zoom: heightToZoom(viewer.camera.positionCartographic.height),
  };
}
function updateSyncedLinks() {
  const center = cameraCenter();
  const activeBasemap = Object.entries(basemaps).find(([_slug, layer]) => layer.show)?.[0] || "aerial";
  const params = new URLSearchParams({
    lat: center.lat.toFixed(5),
    lon: center.lon.toFixed(5),
    z: String(center.zoom),
    basemap: activeBasemap,
    labels: labels.show ? "1" : "0",
  });
  document.querySelectorAll('[data-view-sync="atlas"]').forEach(link => { link.href = `/?${params}`; });
  document.querySelectorAll('[data-view-sync="globe"]').forEach(link => { link.href = `/globe/?${params}`; });
}
viewer.scene.morphComplete.addEventListener(() => {
  const mode = viewer.scene.mode === Cesium.SceneMode.SCENE2D ? "2d" : viewer.scene.mode === Cesium.SceneMode.COLUMBUS_VIEW ? "columbus" : "3d";
  document.querySelectorAll("[data-globe-view]").forEach(button => button.classList.toggle("active", button.dataset.globeView === mode));
  updateSyncedLinks();
});
const imagery = viewer.imageryLayers;
const basemaps = {
  aerial: imagery.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/aerial/{z}/{x}/{y}", maximumLevel: 18, credit: "Esri, Maxar, Earthstar Geographics and contributors"})),
  dark: imagery.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/dark/{z}/{x}/{y}", maximumLevel: 18, credit: "OpenStreetMap contributors, CARTO"}))
};
basemaps.dark.show = false;
if (!basemaps[initialView.basemap]) initialView.basemap = "aerial";
Object.entries(basemaps).forEach(([slug, layer]) => { layer.show = slug === initialView.basemap; });
const study = await Cesium.GeoJsonDataSource.load("/api/layers/study-candidates.geojson", {stroke: Cesium.Color.fromCssColorString("#e6a94a"), strokeWidth: 2, clampToGround: true});
viewer.dataSources.add(study);
const scheme = new Cesium.GeographicTilingScheme();
const gravity = {
  bouguer: imagery.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/gravity-bouguer/{z}/{x}/{y}", tilingScheme: scheme, maximumLevel: 6})),
  isostatic: imagery.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/gravity-isostatic/{z}/{x}/{y}", tilingScheme: scheme, maximumLevel: 6}))
};
Object.values(gravity).forEach(layer => { layer.show = false; layer.alpha = .72; });
const labels = imagery.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/labels/{z}/{x}/{y}", maximumLevel: 18, credit: "OpenStreetMap contributors, CARTO"}));
labels.alpha = .92;
labels.show = initialView.labels;
document.querySelectorAll("[data-globe]").forEach(input => input.addEventListener("change", async () => {
  if (input.dataset.globe === "study") study.show = input.checked;
  else if (input.dataset.globe === "terrain" && token) viewer.terrainProvider = input.checked ? await Cesium.createWorldTerrainAsync() : new Cesium.EllipsoidTerrainProvider();
  else gravity[input.dataset.globe].show = input.checked;
}));
document.querySelectorAll("[data-globe-basemap]").forEach(input => input.addEventListener("change", () => {
  if (!input.checked) return;
  Object.entries(basemaps).forEach(([slug, layer]) => { layer.show = slug === input.dataset.globeBasemap; });
  updateSyncedLinks();
}));
document.querySelectorAll("[data-globe-basemap]").forEach(input => { input.checked = input.dataset.globeBasemap === initialView.basemap; });
const labelInput = document.querySelector("[data-globe-labels]");
if (labelInput) {
  labelInput.checked = labels.show;
  labelInput.addEventListener("change", event => { labels.show = event.target.checked; updateSyncedLinks(); });
}
document.querySelectorAll("[data-globe-view]").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll("[data-globe-view]").forEach(item => item.classList.toggle("active", item === button));
  if (button.dataset.globeView === "2d") viewer.scene.morphTo2D(0.7);
  else if (button.dataset.globeView === "columbus") viewer.scene.morphToColumbusView(0.7);
  else viewer.scene.morphTo3D(0.7);
}));
viewer.camera.setView({
  destination: Cesium.Cartesian3.fromDegrees(initialView.lon, initialView.lat, zoomToHeight(initialView.zoom)),
});
viewer.camera.moveEnd.addEventListener(updateSyncedLinks);
updateSyncedLinks();
})();
