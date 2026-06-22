from fitparse import FitFile
from pathlib import Path
import folium

SEMICIRCLES_TO_DEGREES = 180 / 2**31

files = sorted(Path(".").glob("*.fit"))

all_points = []

print(f"Found {len(files)} FIT files")

for i, file in enumerate(files, start=1):
    print(f"[{i}/{len(files)}] Reading {file.name}...", flush=True)

    fitfile = FitFile(str(file), data_processor=None)

    file_points = []

    for msg in fitfile.get_messages("record"):
        data = {field.name: field.value for field in msg}

        lat = data.get("position_lat")
        lon = data.get("position_long")

        if lat is None or lon is None:
            continue

        lat_deg = lat * SEMICIRCLES_TO_DEGREES
        lon_deg = lon * SEMICIRCLES_TO_DEGREES

        file_points.append((lat_deg, lon_deg))

    print(f"  Points: {len(file_points)}")

    if file_points:
        all_points.extend(file_points)

if not all_points:
    raise RuntimeError("No GPS points found in FIT files.")

center_lat = sum(p[0] for p in all_points) / len(all_points)
center_lon = sum(p[1] for p in all_points) / len(all_points)

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=7,
    tiles="OpenStreetMap"
)

folium.PolyLine(
    all_points,
    weight=3,
    opacity=0.9,
    tooltip="Camino route"
).add_to(m)

folium.Marker(
    all_points[0],
    popup="Start",
    tooltip="Start"
).add_to(m)

folium.Marker(
    all_points[-1],
    popup="Finish",
    tooltip="Finish"
).add_to(m)

m.fit_bounds(all_points)

output_file = "camino_map.html"
m.save(output_file)

print(f"\nSaved map to {output_file}")
