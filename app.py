# FloodSense Pro — Main Flask Application
# All routes for citizen and authority dashboards

from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import sys

# Our modules
from api.weather import get_current_weather, get_forecast, get_weather_for_zones
from ml.predict import predict_risk_from_weather, predict_all_zones, predict_risk
from optimization.allocate import allocate_resources
from routing.evacuation import get_full_evacuation_plan, find_nearest_safe_zones
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# ─── HOME ─────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("home.html")

# ─── CITIZEN ROUTES ───────────────────────────────────────────
@app.route("/citizen")
def citizen_dashboard():
    return render_template("citizen/dashboard.html")

@app.route("/api/citizen/risk")
def get_citizen_risk():
    """
    Main API: Given a city name, return full risk assessment.
    Called by citizen dashboard when user searches a location.
    """
    city = request.args.get("city", "Bengaluru")

    # Step 1: Get live weather
    weather = get_current_weather(city)
    if weather["status"] == "error":
        return jsonify({"status": "error", "message": weather["message"]})

    # Step 2: Find matching zone data (or use defaults)
    zone_data = get_zone_data_for_city(city, weather)

    # Step 3: Predict risk
    prediction = predict_risk_from_weather(weather, zone_data)

    # Step 4: Get evacuation plan if HIGH or EXTREME
    evacuation_plan = None
    if prediction["risk_class"] >= 2:
        evacuation_plan = get_full_evacuation_plan(
            weather["lat"], weather["lon"], city
        )
        # Remove heavy geometry for JSON response
        if evacuation_plan and "primary_safe_zone" in evacuation_plan:
            evac_zone = evacuation_plan["primary_safe_zone"]
            evacuation_plan["primary_safe_zone"] = {
                k: v for k, v in evac_zone.items()
                if k != "route_geometry"
            }

    # Step 5: Get forecast
    forecast_data = get_forecast(city)
    forecast_chart = build_forecast_chart(forecast_data)

    return jsonify({
        "status":          "success",
        "city":            weather["city"],
        "weather":         weather,
        "prediction":      prediction,
        "evacuation_plan": evacuation_plan,
        "forecast_chart":  forecast_chart,
        "emergency_contacts": {
            "NDRF":           "011-24363260",
            "State Disaster": "1070",
            "Ambulance":      "108",
            "Fire":           "101",
            "Police":         "100"
        }
    })

# ─── AUTHORITY ROUTES ─────────────────────────────────────────
@app.route("/authority")
def authority_dashboard():
    return render_template("authority/dashboard.html")

@app.route("/api/authority/zones")
def get_all_zones():
    """
    Returns risk assessment for all Bengaluru zones.
    Used to populate the authority map and zone table.
    """
    # Get weather for all zones
    zones_with_weather = get_weather_for_zones(config.BENGALURU_ZONES)

    # Predict risk for each zone
    zones_with_risk = predict_all_zones(zones_with_weather)

    # Build summary stats
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "EXTREME": 0}
    for z in zones_with_risk:
        risk_counts[z["risk_label"]] += 1

    return jsonify({
        "status":      "success",
        "zones":       zones_with_risk,
        "risk_summary": risk_counts,
        "total_zones": len(zones_with_risk),
        "total_population_at_risk": sum(
            z["population"] for z in zones_with_risk
            if z["risk_class"] >= 2
        )
    })

@app.route("/api/authority/allocate", methods=["POST"])
def run_allocation():
    """
    Run resource optimization for current zone risks.
    Receives available resources from authority user input.
    """
    data = request.get_json()

    available_resources = {
        "ambulances":    int(data.get("ambulances",    45)),
        "boats":         int(data.get("boats",          8)),
        "camp_beds":     int(data.get("camp_beds",   1500)),
        "food_units":    int(data.get("food_units",  5000)),
        "medical_teams": int(data.get("medical_teams", 12)),
    }

    # Get current zone risks
    zones_with_weather = get_weather_for_zones(config.BENGALURU_ZONES)
    zones_with_risk    = predict_all_zones(zones_with_weather)

    # Run optimization
    allocation, summary = allocate_resources(zones_with_risk, available_resources)

    return jsonify({
        "status":     "success",
        "allocation": allocation,
        "summary":    summary,
        "resources_available": available_resources
    })

@app.route("/api/authority/evacuation_route")
def get_evacuation_route_api():
    """Get evacuation route for a specific zone."""
    zone_name = request.args.get("zone", "Bellandur")
    lat = float(request.args.get("lat", 12.9261))
    lon = float(request.args.get("lon", 77.6760))

    plan = get_full_evacuation_plan(lat, lon, zone_name)

    # Remove heavy geometry data
    if plan and "primary_safe_zone" in plan:
        plan["primary_safe_zone"] = {
            k: v for k, v in plan["primary_safe_zone"].items()
            if k != "route_geometry"
        }

    return jsonify({"status": "success", "plan": plan})

# ─── MAP ROUTE ────────────────────────────────────────────────
@app.route("/map")
def risk_map():
    """Generate and serve the live Folium risk map."""
    from maps.risk_map import generate_risk_map
    map_path = generate_risk_map()
    return send_file(map_path)

# ─── PDF REPORT ROUTE ─────────────────────────────────────────
@app.route("/api/authority/report")
def generate_report():
    """Generate and download PDF situation report."""
    from reports.generate_report import create_situation_report
    zones_with_weather = get_weather_for_zones(config.BENGALURU_ZONES)
    zones_with_risk    = predict_all_zones(zones_with_weather)
    pdf_path = create_situation_report(zones_with_risk)
    return send_file(pdf_path, as_attachment=True,
                     download_name="FloodSense_Situation_Report.pdf")

# ─── HELPER FUNCTIONS ─────────────────────────────────────────
def get_zone_data_for_city(city, weather):
    """Match searched city to zone data or return defaults."""
    city_lower = city.lower()
    for zone in config.BENGALURU_ZONES:
        if zone["name"].lower() in city_lower or city_lower in zone["name"].lower():
            return zone
    # Default zone data for cities not in our database
    return {
        "elevation":      300,
        "river_proximity": 5,
        "flood_history":   0.3,
        "population":     50000
    }

def build_forecast_chart(forecast_data):
    """Build chart data for 48-hour rainfall forecast."""
    if forecast_data["status"] == "error":
        return {"labels": [], "rainfall": [], "risk_levels": []}

    labels   = []
    rainfall = []
    risk_levels = []

    for entry in forecast_data["forecast"][:16]:
        # Shorten datetime label
        dt = entry["datetime"]
        label = dt[5:16]  # "MM-DD HH:MM"
        labels.append(label)
        rainfall.append(entry["rainfall_3h"])

        # Simple risk color based on rainfall
        r = entry["rainfall_3h"]
        if r > 50:       risk_levels.append("red")
        elif r > 20:     risk_levels.append("orange")
        elif r > 5:      risk_levels.append("yellow")
        else:            risk_levels.append("green")

    return {
        "labels":      labels,
        "rainfall":    rainfall,
        "risk_levels": risk_levels
    }

# ─── RUN ──────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs("database", exist_ok=True)
    print("\n" + "=" * 50)
    print("  FloodSense Pro — Starting Server")
    print("  Citizen Dashboard : http://127.0.0.1:5000/citizen")
    print("  Authority Dashboard: http://127.0.0.1:5000/authority")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000)