;(async () => {
const token = JSON.parse(document.getElementById("cesium-ion-token").textContent || '""');
if (token) Cesium.Ion.defaultAccessToken = token;
const viewer = new Cesium.Viewer("cesium-globe", {baseLayer: false, baseLayerPicker: false, geocoder: false, animation: false, timeline: false, terrainProvider: new Cesium.EllipsoidTerrainProvider()});
viewer.scene.morphComplete.addEventListener(() => {
  const mode = viewer.scene.mode === Cesium.SceneMode.SCENE2D ? "2d" : viewer.scene.mode === Cesium.SceneMode.COLUMBUS_VIEW ? "columbus" : "3d";
  document.querySelectorAll("[data-globe-view]").forEach(button => button.classList.toggle("active", button.dataset.globeView === mode));
});
const imagery = viewer.imageryLayers;
const basemaps = {
  aerial: imagery.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/aerial/{z}/{x}/{y}", maximumLevel: 18, credit: "Esri, Maxar, Earthstar Geographics and contributors"})),
  dark: imagery.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/dark/{z}/{x}/{y}", maximumLevel: 18, credit: "OpenStreetMap contributors, CARTO"}))
};
basemaps.dark.show = false;
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
document.querySelectorAll("[data-globe]").forEach(input => input.addEventListener("change", async () => {
  if (input.dataset.globe === "study") study.show = input.checked;
  else if (input.dataset.globe === "terrain" && token) viewer.terrainProvider = input.checked ? await Cesium.createWorldTerrainAsync() : new Cesium.EllipsoidTerrainProvider();
  else gravity[input.dataset.globe].show = input.checked;
}));
document.querySelectorAll("[data-globe-basemap]").forEach(input => input.addEventListener("change", () => {
  if (!input.checked) return;
  Object.entries(basemaps).forEach(([slug, layer]) => { layer.show = slug === input.dataset.globeBasemap; });
}));
document.querySelector("[data-globe-labels]")?.addEventListener("change", event => { labels.show = event.target.checked; });
document.querySelectorAll("[data-globe-view]").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll("[data-globe-view]").forEach(item => item.classList.toggle("active", item === button));
  if (button.dataset.globeView === "2d") viewer.scene.morphTo2D(0.7);
  else if (button.dataset.globeView === "columbus") viewer.scene.morphToColumbusView(0.7);
  else viewer.scene.morphTo3D(0.7);
}));
})();
