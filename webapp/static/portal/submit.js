const submitMap = L.map("submit-map").setView([0, 20], 2);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 18, attribution: "© OpenStreetMap contributors"}).addTo(submitMap);
let marker, circle;
const lon = document.getElementById("id_longitude"), lat = document.getElementById("id_latitude"), diameter = document.getElementById("id_diameter_km");
function redraw() {
  if (!lon.value || !lat.value) return;
  const ll = [Number(lat.value), Number(lon.value)];
  marker ? marker.setLatLng(ll) : marker = L.marker(ll, {draggable: true}).addTo(submitMap).on("dragend", e => setPoint(e.target.getLatLng()));
  if (diameter.value) { if (circle) circle.remove(); circle = L.circle(ll, {radius: Number(diameter.value) * 500, color: "#e6a94a", fillOpacity: .08}).addTo(submitMap); }
}
function setPoint(ll) { lat.value = ll.lat.toFixed(6); lon.value = ll.lng.toFixed(6); redraw(); }
submitMap.on("click", e => setPoint(e.latlng));
[lon, lat, diameter].forEach(input => input.addEventListener("input", redraw)); redraw();
