;(async () => {
const token = JSON.parse(document.getElementById("cesium-ion-token").textContent || '""');
if (token) Cesium.Ion.defaultAccessToken = token;
const viewer = new Cesium.Viewer("cesium-globe", {baseLayerPicker: false, geocoder: false, animation: false, timeline: false, terrainProvider: new Cesium.EllipsoidTerrainProvider()});
viewer.imageryLayers.addImageryProvider(new Cesium.OpenStreetMapImageryProvider({url: "https://tile.openstreetmap.org/"}));
const study = await Cesium.GeoJsonDataSource.load("/api/layers/study-candidates.geojson", {stroke: Cesium.Color.fromCssColorString("#e6a94a"), strokeWidth: 2, clampToGround: true});
viewer.dataSources.add(study);
const scheme = new Cesium.GeographicTilingScheme();
const gravity = {
  bouguer: viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/gravity-bouguer/{z}/{x}/{y}", tilingScheme: scheme, maximumLevel: 6})),
  isostatic: viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({url: "/api/raster/tiles/gravity-isostatic/{z}/{x}/{y}", tilingScheme: scheme, maximumLevel: 6}))
};
Object.values(gravity).forEach(layer => { layer.show = false; layer.alpha = .72; });
document.querySelectorAll("[data-globe]").forEach(input => input.addEventListener("change", async () => {
  if (input.dataset.globe === "study") study.show = input.checked;
  else if (input.dataset.globe === "terrain" && token) viewer.terrainProvider = input.checked ? await Cesium.createWorldTerrainAsync() : new Cesium.EllipsoidTerrainProvider();
  else gravity[input.dataset.globe].show = input.checked;
}));
})();
