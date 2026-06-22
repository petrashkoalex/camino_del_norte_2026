from fitparse import FitFile
from pathlib import Path
import folium
import math
import base64

SEMICIRCLES_TO_DEGREES = 180 / 2**31
ROUTE_BLUE = "#3388ff"

def image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


CAMINO_SHELL_BASE64 = image_to_base64("camino_shell.png")


files = sorted(Path(".").glob("*.fit"))

all_points = []
all_elevation_points = []
day_tracks = []
day_end_distances_km = [0]

total_distance_m = 0
total_elapsed_s = 0
total_timer_s = 0
total_ascent_m = 0
total_descent_m = 0

rows = []

print(f"Found {len(files)} FIT files")


def haversine_m(p1, p2):
    lat1, lon1 = p1
    lat2, lon2 = p2
    r = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def fmt_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours} h {minutes:02d} m"


def fmt_pace(minutes_per_km):
    minutes = int(minutes_per_km)
    seconds = int(round((minutes_per_km - minutes) * 60))

    if seconds == 60:
        minutes += 1
        seconds = 0

    return f"{minutes}:{seconds:02d} min/km"


cumulative_distance_m = 0
previous_point = None

for day_number, file in enumerate(files, start=1):
    print(f"[{day_number}/{len(files)}] Reading {file.name}...", flush=True)

    fitfile = FitFile(str(file), data_processor=None)

    distance_m = 0
    elapsed_s = 0
    timer_s = 0
    ascent_m = 0
    descent_m = 0
    file_points = []
    file_elevation_points = []

    for msg in fitfile.get_messages():
        data = {field.name: field.value for field in msg}

        if msg.name == "session":
            distance_m = data.get("total_distance", 0) or 0
            elapsed_s = data.get("total_elapsed_time", 0) or 0
            timer_s = data.get("total_timer_time", 0) or 0
            ascent_m = data.get("total_ascent", 0) or 0
            descent_m = data.get("total_descent", 0) or 0

        elif msg.name == "record":
            lat = data.get("position_lat")
            lon = data.get("position_long")
            altitude = data.get("enhanced_altitude")

            if lat is None or lon is None:
                continue

            lat_deg = lat * SEMICIRCLES_TO_DEGREES
            lon_deg = lon * SEMICIRCLES_TO_DEGREES
            point = (lat_deg, lon_deg)

            if previous_point is not None:
                cumulative_distance_m += haversine_m(previous_point, point)

            previous_point = point
            file_points.append(point)

            if altitude is not None:
                file_elevation_points.append(
                    (cumulative_distance_m / 1000, float(altitude))
                )

    total_distance_m += distance_m
    total_elapsed_s += elapsed_s
    total_timer_s += timer_s
    total_ascent_m += ascent_m
    total_descent_m += descent_m

    day_end_distances_km.append(cumulative_distance_m / 1000)

    all_points.extend(file_points)
    all_elevation_points.extend(file_elevation_points)

    avg_speed = (distance_m / 1000) / (timer_s / 3600) if timer_s else 0
    pace_min_per_km = (timer_s / 60) / (distance_m / 1000) if distance_m else 0

    row = {
        "day": day_number,
        "file": file.name,
        "distance_km": distance_m / 1000,
        "moving_time_s": timer_s,
        "elapsed_time_s": elapsed_s,
        "avg_speed": avg_speed,
        "pace_min_per_km": pace_min_per_km,
        "ascent_m": ascent_m,
        "descent_m": descent_m,
        "points": len(file_points),
    }

    rows.append(row)

    if file_points:
        day_tracks.append({
            "day": day_number,
            "points": file_points,
            "stats": row,
        })


if not rows:
    raise RuntimeError("No valid FIT files found.")

if not all_points:
    raise RuntimeError("No GPS points found in FIT files.")


days_count = len(rows)

avg_day_distance_km = (total_distance_m / 1000) / days_count
avg_day_moving_time_s = total_timer_s / days_count
total_avg_speed = (total_distance_m / 1000) / (total_timer_s / 3600)
total_pace_min_per_km = (total_timer_s / 60) / (total_distance_m / 1000)

longest_day = max(rows, key=lambda r: r["distance_km"])

center_lat = sum(p[0] for p in all_points) / len(all_points)
center_lon = sum(p[1] for p in all_points) / len(all_points)

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=7,
    tiles="OpenStreetMap"
)

for track in day_tracks:
    day = track["day"]
    points = track["points"]
    stats = track["stats"]

    folium.PolyLine(
        points,
        weight=3,
        opacity=0.85,
        color=ROUTE_BLUE,
        interactive=False,
    ).add_to(m)

    end_point = points[-1]

    popup_html = f"""
    <b>Day {day}</b><br>
    Distance: {stats["distance_km"]:.1f} km<br>
    Moving Time: {fmt_time(stats["moving_time_s"])}<br>
    Avg Speed: {stats["avg_speed"]:.2f} km/h<br>
    Pace: {fmt_pace(stats["pace_min_per_km"])}<br>
    Ascent: {stats["ascent_m"]:.0f} m<br>
    Descent: {stats["descent_m"]:.0f} m
    """

    day_icon_html = f"""
    <div style="
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: {ROUTE_BLUE};
        color: white;
        border: 2px solid white;
        box-shadow: 0 1px 6px rgba(0,0,0,0.45);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: bold;
        font-family: Arial, sans-serif;
    ">
        {day}
    </div>
    """

    folium.Marker(
        location=end_point,
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=f"End of Day {day}",
        icon=folium.DivIcon(
            html=day_icon_html,
            icon_size=(24, 24),
            icon_anchor=(12, 12),
        ),
    ).add_to(m)

folium.Marker(
    all_points[0],
    popup="Start",
    tooltip="Start",
    icon=folium.Icon(icon="play", prefix="fa"),
).add_to(m)

folium.Marker(
    all_points[-1],
    popup="Finish",
    tooltip="Finish",
    icon=folium.Icon(icon="flag-checkered", prefix="fa"),
).add_to(m)


# Push the route visually into the upper part of the screen
min_lat = min(p[0] for p in all_points)
max_lat = max(p[0] for p in all_points)
min_lon = min(p[1] for p in all_points)
max_lon = max(p[1] for p in all_points)

lat_span = max_lat - min_lat
extra_space_below = lat_span * 2.8

custom_bounds = [
    [min_lat - extra_space_below, min_lon],
    [max_lat, max_lon],
]

m.fit_bounds(custom_bounds)


def build_elevation_svg(elevation_points, day_end_distances_km, width=1200, height=180):
    if not elevation_points:
        return "<p>No elevation data found.</p>"

    max_points = 1200
    step = max(1, len(elevation_points) // max_points)
    pts = elevation_points[::step]

    min_dist = min(d for d, e in pts)
    max_dist = max(d for d, e in pts)

    min_ele = 0
    max_ele = max(e for d, e in pts)

    padding_left = 55
    padding_right = 20
    padding_top = 20
    padding_bottom = 35

    plot_w = width - padding_left - padding_right
    plot_h = height - padding_top - padding_bottom

    def x_scale(d):
        return padding_left + ((d - min_dist) / (max_dist - min_dist)) * plot_w

    def y_scale(e):
        return padding_top + (1 - ((e - min_ele) / (max_ele - min_ele))) * plot_h

    polyline = " ".join(
        f"{x_scale(d):.1f},{y_scale(e):.1f}"
        for d, e in pts
    )

    day_ticks = ""
    for day, dist_km in enumerate(day_end_distances_km):
        x = x_scale(dist_km)

        if day == 0 or day == len(day_end_distances_km) - 1 or day % 5 == 0:
            day_ticks += f"""
            <line x1="{x:.1f}" y1="{padding_top + plot_h}" x2="{x:.1f}" y2="{padding_top + plot_h + 5}" stroke="#777" stroke-width="1" />
            <text x="{x:.1f}" y="{height - 8}" font-size="12" fill="#555" text-anchor="middle">{day}</text>
            """

    y_min = y_scale(min_ele)
    y_max = y_scale(max_ele)

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}">
        <rect x="0" y="0" width="{width}" height="{height}" fill="white" />

        <line x1="{padding_left}" y1="{padding_top}" x2="{padding_left}" y2="{padding_top + plot_h}" stroke="#999" stroke-width="1" />
        <line x1="{padding_left}" y1="{padding_top + plot_h}" x2="{padding_left + plot_w}" y2="{padding_top + plot_h}" stroke="#999" stroke-width="1" />

        {day_ticks}

        <text x="{padding_left}" y="24" font-size="24" font-weight="bold" fill="#222">
            Elevation profile by day
        </text>

        <text x="8" y="{y_max + 4:.1f}" font-size="12" fill="#555">{max_ele:.0f} m</text>
        <text x="8" y="{y_min + 4:.1f}" font-size="12" fill="#555">0 m</text>

        <polyline points="{polyline}" fill="none" stroke="{ROUTE_BLUE}" stroke-width="2.5" />

        <text x="{padding_left + plot_w / 2}" y="{height - 8}" font-size="12" fill="#555" text-anchor="middle">
            Day number
        </text>
    </svg>
    """


elevation_svg = build_elevation_svg(
    all_elevation_points,
    day_end_distances_km
)

stats_html = f"""
<style>
    .stats-panel {{
        position: fixed;
        left: 20px;
        bottom: 20px;
        width: 320px;
        height: 455px;
        overflow-y: scroll;
        z-index: 9999;
        background: white;
        padding: 18px 20px;
        border-radius: 14px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.25);
        font-family: Arial, sans-serif;
        font-size: 14px;
        max-height: 55vh;

    }}

    .life-panel {{
        position: fixed;
        left: 380px;
        bottom: 20px;
        width: 320px;
        height: 455px;
        overflow-y: scroll;
        z-index: 9999;
        background: white;
        padding: 18px 20px;
        border-radius: 14px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.25);
        font-family: Arial, sans-serif;
        font-size: 14px;
        max-height: 55vh;
    }}

    .stats-panel img {{
        max-width: 64px;
        height: auto;

    }}


    .mobile-life {{
        display: none;
    }}

    .life-panel img {{
       max-width: 64px;
       height: auto;
    }}

    .fullscreen-button {{
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 9999;
    }}

    .fullscreen-button button {{
        background: white;
        border: none;
        border-radius: 10px;
        padding: 10px 14px;
        cursor: pointer;
        box-shadow: 0 2px 12px rgba(0,0,0,.25);
        font-family: Arial, sans-serif;
        font-size: 14px;
    }}

    .elevation-panel {{
        position: fixed;
        left: 740px;
        right: 20px;
        bottom: 20px;
        z-index: 9999;
        background: white;
        padding: 10px 14px;
        border-radius: 14px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.25);
        font-family: Arial, sans-serif;
    }}

   @media (max-width: 700px) {{

      .stats-panel {{
        left: 10px;
        right: 10px;
        bottom: 10px;
        top: auto;

        width: auto;
        height: auto;

        max-height: 30vh;

        overflow-y: scroll;

        font-size: 12px;
        padding: 12px 14px;
    }}

    .life-panel {{
        display: none;
    }}

    .elevation-panel {{
        display: none;
    }}

    .fullscreen-button {{
        display: none;
    }}

    .mobile-life {{
        display: block;
    }}


}}
</style>

<div class="stats-panel">

    <h2 style="margin: 0 0 4px 0;">🥾 Camino del Norte</h2>
    <div style="margin: 0 0 12px 0; color: #555; font-size: 13px;">
        + Muxía + Finisterre
    </div>

    <div style="margin: 0 0 12px 0; color: #555; font-size: 13px;">
        20 Apr 2026 – 22 May 2026
    </div><br>

    <b>Distance:</b> {total_distance_m / 1000:.1f} km<br>
    <b>Total Ascent:</b> {total_ascent_m:,.0f} m<br>
    <b>Total Descent:</b> {total_descent_m:,.0f} m<br>
    🏔 Climbed Everest 2.5 times<br><br>
    <b>Days:</b> {days_count}<br>
    <b>Moving Time:</b> {fmt_time(total_timer_s)} (9.7 days of continuous walking)<br>
    <b>Average Moving Speed:</b> {total_avg_speed:.2f} km/h ({fmt_pace(total_pace_min_per_km)})<br>
    <b>Average Daily Distance:</b> {avg_day_distance_km:.1f} km<br>
    <b>Average Daily Moving Time:</b> {fmt_time(avg_day_moving_time_s)}<br>
    <b>Longest Day:</b><br>
    {longest_day["distance_km"]:.1f} km<br>
    {fmt_time(longest_day["moving_time_s"])}<br>


<div class="mobile-life">


<div style="
    display:flex;
    align-items:center;
    justify-content:space-between;
    margin-bottom:20px;
">
    <h2 style="margin:0;">
        Camino Life
    </h2>

    <img
            src="data:image/png;base64,{CAMINO_SHELL_BASE64}"
            alt="Camino shell"
            style="width:64px;height:auto;"
        >
</div>

    <b>People:</b><br>
    🌍 Met people from 26 countries<br><br>

    <b>Accommodation:</b><br>
    🏠 22 nights in albergues<br>
    🏨 9 nights in hotels<br>
    🛏️ 3 nights in hostels<br>
    🏡 1 night with a local host<br><br>


    <b>Drinks:</b><br>
    🍎 23 glasses of sidra<br>
    🍷 19 glasses of wine<br>
    🍺 16 glasses of beer<br><br>

    <b>👣 Steps:</b><br>
    1,360,053 total steps<br>
    41,214 average daily steps<br>
    70,306 longest day
</div>

</div>
"""

life_html = f"""

<div class="life-panel">

  <div style="
    display:flex;
    align-items:center;
    justify-content:space-between;
    margin-bottom:20px;
">
    <h2 style="margin:0;">
        Camino Life
    </h2>

    <img
            src="data:image/png;base64,{CAMINO_SHELL_BASE64}"
            alt="Camino shell"
            style="width:64px;height:auto;"
        >
</div>


   <b>People:</b><br>
    🌍 Met people from 26 countries<br><br>

    <b>Accommodation:</b><br>
    🏠 22 nights in albergues<br>
    🏨 9 nights in hotels<br>
    🛏️ 3 nights in hostels<br>
    🏡 1 night with a local host<br><br>


    <b>Drinks:</b><br>
    🍎 23 glasses of sidra<br>
    🍷 19 glasses of wine<br>
    🍺 16 glasses of beer<br><br>

    <b>👣 Steps:</b><br>
    1,360,053 total steps<br>
    41,214 average daily steps<br>
    70,306 longest day
</div>
"""

fullscreen_button = """
<div class="fullscreen-button">
    <button onclick="
        const map = document.querySelector('.leaflet-container');
        if (map.requestFullscreen) {
            map.requestFullscreen();
        } else if (map.webkitRequestFullscreen) {
            map.webkitRequestFullscreen();
        }
    ">
        ⛶ Open Full Screen Map
    </button>
</div>
"""

elevation_html = f"""
<div class="elevation-panel">
    {elevation_svg}
</div>
"""

m.get_root().html.add_child(folium.Element(stats_html))
m.get_root().html.add_child(folium.Element(life_html))
m.get_root().html.add_child(folium.Element(fullscreen_button))
m.get_root().html.add_child(folium.Element(elevation_html))

meta_html = """
<title>Camino del Norte + Muxía + Finisterre</title>

<meta name="description" content="1010.8 km • 33 days • 22,463 m ascent • 1,360,053 steps">

<meta property="og:title" content="Camino del Norte + Muxía + Finisterre">
<meta property="og:description" content="1010.8 km • 33 days • 22,463 m ascent • 1,360,053 steps">
<meta property="og:type" content="website">
<meta property="og:url" content="https://petrashkoalex.github.io/camino_del_norte_2026/">
<meta property="og:image" content="https://petrashkoalex.github.io/camino_del_norte_2026/preview.png">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Camino del Norte + Muxía + Finisterre">
<meta name="twitter:description" content="1010.8 km • 33 days • 22,463 m ascent • 1,360,053 steps">
<meta name="twitter:image" content="https://petrashkoalex.github.io/camino_del_norte_2026/preview.png">

<link rel="icon" type="image/png" href="favicon.png">
"""

m.get_root().header.add_child(folium.Element(meta_html))

output_file = "camino_report.html"
m.save(output_file)

print(f"\\nSaved report to {output_file}")