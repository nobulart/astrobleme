from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from pyproj import CRS, Transformer
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from .geometry import Candidate


KML_NS = {"k": "http://earth.google.com/kml/2.2"}


@dataclass
class Province:
    geometry: MultiPolygon | Polygon
    properties: dict


def _coordinates(text: str):
    values = []
    for token in (text or "").replace("\n", " ").split():
        parts = token.split(",")
        if len(parts) >= 2:
            values.append((float(parts[0]), float(parts[1])))
    return values


def _description_fields(text: str):
    clean = html.unescape(re.sub(r"<[^>]+>", "\n", text or ""))
    fields = {}
    for line in clean.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def load_provinces(path: str | Path) -> list[Province]:
    root = ET.parse(path).getroot()
    provinces = []
    for placemark in root.findall(".//k:Placemark", KML_NS):
        props = _description_fields(placemark.findtext("k:description", default="", namespaces=KML_NS))
        props["name"] = placemark.findtext("k:name", default="", namespaces=KML_NS)
        polygons = []
        for element in placemark.findall(".//k:Polygon", KML_NS):
            outer_text = element.findtext("k:outerBoundaryIs/k:LinearRing/k:coordinates", default="", namespaces=KML_NS)
            outer = _coordinates(outer_text)
            holes = []
            for inner in element.findall("k:innerBoundaryIs/k:LinearRing/k:coordinates", KML_NS):
                holes.append(_coordinates(inner.text or ""))
            if len(outer) >= 4:
                polygon = Polygon(outer, holes)
                if not polygon.is_valid:
                    polygon = polygon.buffer(0)
                if not polygon.is_empty:
                    polygons.append(polygon)
        if polygons:
            geom = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
            provinces.append(Province(geom, props))
    return provinces


class GeologyIndex:
    def __init__(self, path: str | Path):
        self.provinces = load_provinces(path)
        self.geometries = []
        self.metadata = []
        for province in self.provinces:
            for shift in (-360.0, 0.0, 360.0):
                geom = affinity.translate(province.geometry, xoff=shift)
                self.geometries.append(geom)
                self.metadata.append(province.properties)
        self.tree = STRtree(self.geometries)

    def score(self, candidate: Candidate) -> dict:
        radius = max(candidate.radius_km, 1.0)
        buffer_km = max(5.0, min(50.0, 0.05 * radius))
        degree_margin = buffer_km / 80.0
        envelope = box(*candidate.geometry.bounds).buffer(degree_margin)
        indices = self.tree.query(envelope)
        if len(indices) == 0:
            return {
                "geology_boundary_coincidence": 0.0,
                "geology_independence": 1.0,
                "geology_boundary_crossings": 0,
                "geology_nearby_boundaries": 0,
                "geology_nearby_types": "",
            }

        local_crs = CRS.from_proj4(
            f"+proj=aeqd +lat_0={candidate.lat:.10f} +lon_0={candidate.lon:.10f} +datum=WGS84 +units=m +no_defs"
        )
        transformer = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)
        project = transformer.transform
        arc_local = transform(project, candidate.geometry)
        boundary_parts = []
        types = set()
        for idx in indices:
            geom = self.geometries[int(idx)]
            clipped = geom.boundary.intersection(envelope)
            if clipped.is_empty:
                continue
            boundary_parts.append(transform(project, clipped))
            value = self.metadata[int(idx)].get("prov_type")
            if value and value != "NULL":
                types.add(value)
        if not boundary_parts:
            return {
                "geology_boundary_coincidence": 0.0,
                "geology_independence": 1.0,
                "geology_boundary_crossings": 0,
                "geology_nearby_boundaries": 0,
                "geology_nearby_types": "",
            }
        boundaries = unary_union(boundary_parts)
        buffered = boundaries.buffer(buffer_km * 1000.0)
        overlap = arc_local.intersection(buffered).length
        coincidence = float(min(1.0, overlap / max(arc_local.length, 1e-9)))
        intersections = arc_local.intersection(boundaries)
        if intersections.is_empty:
            crossings = 0
        elif intersections.geom_type == "Point":
            crossings = 1
        elif hasattr(intersections, "geoms"):
            crossings = len(intersections.geoms)
        else:
            crossings = 1
        return {
            "geology_boundary_coincidence": coincidence,
            "geology_independence": 1.0 - coincidence,
            "geology_boundary_crossings": int(crossings),
            "geology_nearby_boundaries": int(len(boundary_parts)),
            "geology_nearby_types": ";".join(sorted(types)),
        }
