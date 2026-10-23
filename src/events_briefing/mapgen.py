"""Self-contained HTML map. Offline mode does not request tiles."""

from __future__ import annotations

import html
import json

from events_briefing.models import RankedIncident

ATTRIBUTION = (
    "Offline schematic. Positions use coordinates rounded to 2 decimal degrees "
    "(about 1.1 km) or a borough centroid when the source has no point (FDNY). "
    "No basemap tiles are requested. The tile attribution control credits "
    "OpenStreetMap contributors: https://www.openstreetmap.org/copyright"
)
TILE_ATTRIBUTION_HTML = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
)

_LAT_MIN = 40.49
_LAT_MAX = 40.92
_LON_MIN = -74.26
_LON_MAX = -73.70


def render_map(ranked: list[RankedIncident], *, title: str) -> str:
    points: list[dict[str, object]] = []
    clusters: dict[str, int] = {}
    for item in ranked:
        incident = item.incident
        key = incident.geohash6 or incident.borough or "unknown"
        clusters[key] = clusters.get(key, 0) + 1
        if incident.lat_rounded is None or incident.lon_rounded is None:
            continue
        points.append(
            {
                "rank": item.rank,
                "id": incident.id,
                "group": incident.category_group.value,
                "category": incident.category,
                "borough": incident.borough,
                "lat": incident.lat_rounded,
                "lon": incident.lon_rounded,
                "precision": incident.location_precision.value,
                "score": item.score,
            }
        )
    data = json.dumps(
        {"points": points, "bounds": [_LAT_MIN, _LAT_MAX, _LON_MIN, _LON_MAX]}
    ).replace("<", "\\u003c")
    rows = "\n".join(_row(item) for item in ranked[:30])
    cluster_rows = "\n".join(
        f"<li>{html.escape(key)}: {count}</li>" for key, count in sorted(clusters.items())
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{html.escape(title)}</title>
<style>
body {{ font-family: sans-serif; margin: 1rem; color: #1b1b1b; }}
.layout {{ display: flex; gap: 1rem; align-items: flex-start; flex-wrap: wrap; }}
.map-frame {{ position: relative; display: inline-block; }}
canvas {{ border: 1px solid #ccc; background: #f4f7f8; display: block; }}
.leaflet-bottom.leaflet-right {{ position: absolute; right: 0; bottom: 0; z-index: 2; }}
.leaflet-control-attribution {{
  background: rgba(255, 255, 255, 0.9);
  padding: 0 0.4rem;
  font-size: 12px;
}}
table {{ border-collapse: collapse; font-size: 14px; }}
td, th {{ border-bottom: 1px solid #ddd; padding: 0.3rem 0.5rem; text-align: left; }}
.note {{ max-width: 70ch; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p class="note">{html.escape(ATTRIBUTION)}</p>
<div class="layout">
<div class="map-frame">
<canvas id="map" width="640" height="720"></canvas>
<div class="leaflet-control-container">
<div class="leaflet-bottom leaflet-right">
<div class="leaflet-control-attribution leaflet-control" role="contentinfo">
{TILE_ATTRIBUTION_HTML}
</div>
</div>
</div>
</div>
<div>
<h2>Ranked list</h2>
<table>
<thead><tr><th>Rank</th><th>Group</th><th>Category</th><th>Borough</th><th>Id</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<h2>Clusters</h2>
<ul>
{cluster_rows}
</ul>
</div>
</div>
<script id="map-data" type="application/json">{data}</script>
<script>
const payload = JSON.parse(document.getElementById("map-data").textContent);
const canvas = document.getElementById("map");
const ctx = canvas.getContext("2d");
const [latMin, latMax, lonMin, lonMax] = payload.bounds;
function xOf(lon) {{ return 24 + (lon - lonMin) / (lonMax - lonMin) * (canvas.width - 48); }}
function yOf(lat) {{ return 24 + (latMax - lat) / (latMax - latMin) * (canvas.height - 48); }}
const colors = {{
  life_safety: "#b00020",
  property: "#8a5a00",
  quality_of_life: "#1d4e89",
  other: "#555",
  noise: "#2e7d32"
}};
ctx.fillStyle = "#102030";
ctx.font = "14px sans-serif";
ctx.fillText("NYC schematic (coarse positions)", 24, 18);
for (const point of payload.points) {{
  ctx.beginPath();
  ctx.fillStyle = colors[point.group] || "#333";
  const radius = point.precision === "borough_centroid" ? 8 : 5;
  ctx.arc(xOf(point.lon), yOf(point.lat), radius, 0, Math.PI * 2);
  ctx.fill();
}}
</script>
</body>
</html>
"""


def _row(item: RankedIncident) -> str:
    incident = item.incident
    borough = incident.borough or ""
    return (
        "<tr>"
        f"<td>{item.rank}</td>"
        f"<td>{html.escape(incident.category_group.value)}</td>"
        f"<td>{html.escape(incident.category)}</td>"
        f"<td>{html.escape(borough)}</td>"
        f"<td>{html.escape(incident.id)}</td>"
        "</tr>"
    )
