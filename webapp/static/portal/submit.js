const submitMap = L.map("submit-map").setView([0, 20], 2);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18, attribution: "© OpenStreetMap contributors"}).addTo(submitMap);
let marker, circle;
const geometry = document.getElementById("id_geometry_text");
const lon = document.getElementById("id_longitude"), lat = document.getElementById("id_latitude"), diameter = document.getElementById("id_diameter_km");
const centerMarkerIcon = L.divIcon({className: "candidate-center-marker selected", html: "+", iconSize: [16, 16], iconAnchor: [8, 8]});
function circleGeometry(lng, latitude, diameterKm) {
  const angular = (diameterKm / 2) / 6371.0088, lat1 = latitude * Math.PI / 180, lon1 = lng * Math.PI / 180, coordinates = [];
  for (let i = 0; i <= 72; i++) { const b = 2 * Math.PI * i / 72; const lat2 = Math.asin(Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(b)); const lon2 = lon1 + Math.atan2(Math.sin(b) * Math.sin(angular) * Math.cos(lat1), Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2)); coordinates.push([((lon2 * 180 / Math.PI + 540) % 360) - 180, lat2 * 180 / Math.PI]); }
  return {type: "LineString", coordinates};
}
function redraw() {
  if (!lon.value || !lat.value) return;
  const ll = [Number(lat.value), Number(lon.value)];
  marker ? marker.setLatLng(ll) : marker = L.marker(ll, {draggable: true, icon: centerMarkerIcon}).addTo(submitMap).on("dragend", e => setPoint(e.target.getLatLng()));
  if (diameter.value) { if (circle) circle.remove(); circle = L.circle(ll, {radius: Number(diameter.value) * 500, color: "#e6a94a", fillOpacity: .08}).addTo(submitMap); if (geometry && !geometry.dataset.userTrace) geometry.value = JSON.stringify(circleGeometry(Number(lon.value), Number(lat.value), Number(diameter.value))); }
}
function setPoint(ll) { lat.value = ll.lat.toFixed(6); lon.value = ll.lng.toFixed(6); redraw(); }
submitMap.on("click", e => setPoint(e.latlng));
[lon, lat, diameter].forEach(input => input.addEventListener("input", redraw)); redraw();
