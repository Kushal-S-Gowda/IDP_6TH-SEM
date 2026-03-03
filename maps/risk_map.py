# FloodSense Pro — Folium Risk Map Generator

import folium
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from api.weather import get_weather_for_zones
from ml.predict import predict_all_zones

RISK_COLORS = {
    "LOW":     "#28a745",
    "MEDIUM":  "#ffc107",
    "HIGH":    "#fd7e14",
    "EXTREME": "#dc3545"
}

RISK_ICONS = {
    "LOW":     "✅",
    "MEDIUM":  "⚠️",
    "HIGH":    "🟠",
    "EXTREME": "🔴"
}

def generate_risk_map():
    """
    Generates interactive Folium map with:
    - Color coded risk zones
    - Clickable popups with zone details
    - Safe zone markers
    - Risk legend
    Returns path to saved HTML file.
    """
    print("Generating live risk map...")

    # Get live data for all zones
    zones_with_weather = get_weather_for_zones(config.BENGALURU_ZONES)
    zones_with_risk    = predict_all_zones(zones_with_weather)

    # Create base map centered on Bengaluru
    m = folium.Map(
        location=config.BENGALURU_COORDS,
        zoom_start=11,
        tiles="CartoDB dark_matter"
    )

    # Add title
    title_html = """
    <div style="position:fixed; top:10px; left:50%; transform:translateX(-50%);
                z-index:1000; background:rgba(10,22,40,0.92);
                border:2px solid #1565c0; border-radius:12px;
                padding:10px 25px; text-align:center;">
        <span style="color:#4fc3f7; font-size:1.1rem; font-weight:900;">
            🌊 FloodSense Pro — Live Risk Map
        </span><br>
        <span style="color:#90caf9; font-size:0.75rem;">
            Bengaluru Zone Risk Assessment | Real-Time Data
        </span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    # Add risk zone markers
    for zone in zones_with_risk:
        risk_label = zone.get("risk_label", "LOW")
        color      = RISK_COLORS.get(risk_label, "#28a745")
        icon_text  = RISK_ICONS.get(risk_label, "✅")

        # Pulse effect for HIGH and EXTREME zones
        radius = 600 if risk_label in ["HIGH", "EXTREME"] else 400
        fill_opacity = 0.7 if risk_label in ["HIGH", "EXTREME"] else 0.5

        # Main risk circle
        folium.CircleMarker(
            location=[zone["lat"], zone["lon"]],
            radius=18,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=fill_opacity,
            weight=3,
            popup=folium.Popup(
                f"""
                <div style="font-family:Arial; min-width:200px;">
                    <h4 style="color:{color}; margin:0 0 8px 0;">
                        {icon_text} {zone['name']}
                    </h4>
                    <table style="width:100%; font-size:0.85rem;">
                        <tr><td><b>Risk Level</b></td><td style="color:{color};">
                            <b>{risk_label}</b></td></tr>
                        <tr><td><b>AI Confidence</b></td>
                            <td>{zone.get('risk_score', 0)}%</td></tr>
                        <tr><td><b>Population</b></td>
                            <td>{zone.get('population', 0):,}</td></tr>
                        <tr><td><b>Temperature</b></td>
                            <td>{zone.get('temperature', 0)}°C</td></tr>
                        <tr><td><b>Rainfall</b></td>
                            <td>{zone.get('rainfall_1h', 0)} mm/hr</td></tr>
                        <tr><td><b>Humidity</b></td>
                            <td>{zone.get('humidity', 0)}%</td></tr>
                        <tr><td><b>Wind Speed</b></td>
                            <td>{zone.get('wind_speed', 0)} km/h</td></tr>
                        <tr><td><b>Action</b></td>
                            <td style="color:#ff9800; font-size:0.8rem;">
                            {zone.get('action', '')}</td></tr>
                    </table>
                </div>
                """,
                max_width=280
            ),
            tooltip=f"{zone['name']} — {risk_label} RISK"
        ).add_to(m)

        # Zone name label
        folium.Marker(
            location=[zone["lat"], zone["lon"]],
            icon=folium.DivIcon(
                html=f"""<div style="
                    font-size:0.7rem; font-weight:700;
                    color:white; text-align:center;
                    text-shadow: 1px 1px 2px black;
                    margin-top: 22px; white-space:nowrap;">
                    {zone['name']}
                </div>""",
                icon_size=(120, 20),
                icon_anchor=(60, 0)
            )
        ).add_to(m)

    # Add safe zone markers
    for sz in config.SAFE_ZONES_BENGALURU:
        folium.Marker(
            location=[sz["lat"], sz["lon"]],
            icon=folium.DivIcon(
                html=f"""<div style="
                    background: rgba(40,167,69,0.9);
                    border: 2px solid #28a745;
                    border-radius: 6px;
                    padding: 3px 7px;
                    font-size: 0.65rem;
                    font-weight: 700;
                    color: white;
                    white-space: nowrap;">
                    🏔️ {sz['name']}
                </div>""",
                icon_size=(150, 25),
                icon_anchor=(75, 12)
            ),
            popup=folium.Popup(
                f"""
                <div style="font-family:Arial;">
                    <h4 style="color:#28a745;">🏔️ Safe Zone</h4>
                    <b>{sz['name']}</b><br>
                    Elevation: {sz['elevation']}m<br>
                    Capacity: {sz['capacity']:,} people
                </div>
                """,
                max_width=200
            ),
            tooltip=f"🏔️ Safe Zone: {sz['name']}"
        ).add_to(m)

    # Add legend
    legend_html = """
    <div style="position:fixed; bottom:20px; right:10px;
                z-index:1000; background:rgba(10,22,40,0.92);
                border:1px solid #1565c0; border-radius:10px;
                padding:12px 16px; font-family:Arial;">
        <p style="color:#4fc3f7; font-weight:700;
                  margin:0 0 8px 0; font-size:0.85rem;">
            Risk Levels
        </p>
        <div style="color:white; font-size:0.8rem; line-height:1.8;">
            <span style="color:#28a745;">●</span> LOW — Normal conditions<br>
            <span style="color:#ffc107;">●</span> MEDIUM — Monitor closely<br>
            <span style="color:#fd7e14;">●</span> HIGH — Begin evacuation<br>
            <span style="color:#dc3545;">●</span> EXTREME — Emergency protocol<br>
            <span style="color:#28a745;">▪</span> Safe Zones
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save map
    os.makedirs("static", exist_ok=True)
    map_path = "static/risk_map.html"
    m.save(map_path)
    print(f"  Map saved → {map_path}")
    return map_path


if __name__ == "__main__":
    path = generate_risk_map()
    print(f"✅ Map generated → {path}")
    print("   Open static/risk_map.html in browser to preview")