# FloodSense Pro — Main Flask Application
# All routes for citizen and authority dashboards

from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import sys
from datetime import datetime

import requests

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
# ─── SIMULATION ROUTE ────────────────────────────────────────
@app.route("/simulation")
def simulation_page():
    return render_template("simulation.html")

@app.route("/api/simulate")
def simulate():
    """Run prediction with custom parameters for demo simulation."""
    rainfall_24h        = float(request.args.get("rainfall_24h", 5))
    rainfall_7d         = float(request.args.get("rainfall_7d", 20))
    temperature         = float(request.args.get("temperature", 28))
    humidity            = float(request.args.get("humidity", 60))
    wind_speed          = float(request.args.get("wind_speed", 10))
    elevation           = float(request.args.get("elevation", 900))
    river_proximity     = float(request.args.get("river_proximity", 5))
    flood_history_freq  = float(request.args.get("flood_history_freq", 0.7))
    soil_saturation_idx = float(request.args.get("soil_saturation_idx", 0.04))
    population_density  = float(request.args.get("population_density", 35000))

    prediction = predict_risk(
        rainfall_24h, rainfall_7d, temperature, humidity,
        wind_speed, elevation, river_proximity,
        flood_history_freq, soil_saturation_idx, population_density
    )
    return jsonify({"status": "success", "prediction": prediction})
@app.route("/trends")
def trends_page():
    return render_template("trends.html")
# ─── RESCUE CAMP FINDER ───────────────────────────────────────
@app.route("/rescue")
def rescue_page():
    return render_template("rescue.html")

@app.route("/api/rescue/camps")
def get_rescue_camps():
    """
    Returns all safe zones ranked by distance, time,
    capacity and overall score from a given origin.
    """
    lat       = float(request.args.get("lat", 12.9261))
    lon       = float(request.args.get("lon", 77.6760))
    zone_name = request.args.get("zone", "Your Location")

    from geopy.distance import geodesic
    import openrouteservice

    client = openrouteservice.Client(key=config.OPENROUTE_API_KEY)

    camps = []
    for sz in config.SAFE_ZONES_BENGALURU:
        try:
            # Real road route via OpenRouteService
            coords = ((lon, lat), (sz["lon"], sz["lat"]))
            route  = client.directions(
                        coords,
                         profile="driving-car",
         radiuses=[1000, 1000]  # snap to nearest road within 1km
)
            dist_km  = round(route["routes"][0]["summary"]["distance"] / 1000, 2)
            dur_min  = round(route["routes"][0]["summary"]["duration"] / 60, 1)
        except:
            # Fallback to straight line
            dist_km = round(geodesic((lat,lon),(sz["lat"],sz["lon"])).km, 2)
            dur_min = round(dist_km * 2.5, 1)

        # Services based on name
        services = []
        name = sz["name"].lower()
        if any(x in name for x in ["medical","hospital","nimhans","john"]):
            services.extend(["medical","food"])
        else:
            services.extend(["shelter","food"])
        if "camp" in name or "palace" in name or "lalbagh" in name:
            services.append("boats")
        if "nandi" in name or "palace" in name or "manipal" in name:
            services.append("helicopter")
        if "medical" not in services and any(
            x in name for x in ["camp","palace","lalbagh","nimhans"]):
            services.append("medical")
        services = list(set(services))

        # Occupancy simulation
        import random
        random.seed(hash(sz["name"]) % 100)
        occupancy = random.randint(10, 55)

        # Overall score (0-100)
        # Lower distance = better, higher elevation = better,
        # lower occupancy = better, more services = better
        dist_score      = max(0, 100 - dist_km * 3)
        dur_score       = max(0, 100 - dur_min * 1.5)
        elev_score      = min(100, sz["elevation"] / 15)
        occupancy_score = 100 - occupancy
        service_score   = len(services) * 15
        capacity_score  = min(100, sz["capacity"] / 100)

        overall = round(
            dist_score * 0.30 +
            dur_score  * 0.25 +
            elev_score * 0.15 +
            occupancy_score * 0.15 +
            service_score   * 0.10 +
            capacity_score  * 0.05
        )

        camps.append({
            **sz,
            "road_distance_km":  dist_km,
            "road_duration_min": dur_min,
            "services":          services,
            "occupancy_pct":     occupancy,
            "overall_score":     min(99, overall),
            "description": get_camp_description(sz["name"])
        })

    # Sort by overall score
    camps.sort(key=lambda x: x["overall_score"], reverse=True)

    return jsonify({"status": "success", "camps": camps,
                    "origin": zone_name})

def get_camp_description(name):
    descriptions = {
        "Nandi Hills":
            "Highest safe point near Bengaluru. Primary evacuation destination for extreme floods.",
        "Lalbagh Botanical Garden":
            "Central Bengaluru relief hub. BBMP managed. Medical teams on standby.",
        "Palace Grounds":
            "Large open grounds. Helipad available. Army coordination point.",
        "NICE Grounds Bidadi":
            "South-west Bengaluru relief point. Accessible via NICE Road.",
        "NIMHANS Convention Centre":
            "BBMP designated shelter. Adjacent to NIMHANS hospital.",
        "St. John's Medical College":
            "Emergency medical facility. Priority for injured evacuees.",
        "Manipal Hospital":
            "Trauma and emergency care centre. Air ambulance helipad available.",
        "BBMP Relief Camp 1":
            "North Bengaluru BBMP camp. Rescue boats stationed for water rescue.",
        "BBMP Relief Camp 2":
            "South Bengaluru camp. Closest to Bellandur and HSR Layout zones.",
        "BBMP Relief Camp 3":
            "East Bengaluru camp. Closest to Whitefield and Marathahalli zones.",
    }
    return descriptions.get(name, "BBMP designated flood relief centre.")
# ═══════════════════════════════════════════════════════════════════
#  FIRE SIMULATION — ADD THIS ENTIRE BLOCK TO YOUR app.py
#  Paste it just BEFORE the line:  if __name__ == "__main__":
# ═══════════════════════════════════════════════════════════════════

# ── NEW IMPORT (add at top of app.py with other imports) ────────────
# import requests   ← you likely already have this

# ── ROUTE: Fire Simulation Page ─────────────────────────────────────
@app.route("/fire-simulation")
def fire_simulation():
    return render_template("fire_simulation.html")


# ── API: Live fire conditions (feeds real wind/weather to the sim) ──
@app.route("/api/fire/conditions")
def get_fire_conditions():
    """
    Returns live weather conditions for the fire simulation.
    Pulls real wind speed & direction from OpenWeatherMap for Bengaluru.
    The JS simulation uses these as initial parameters.
    """
    import math

    try:
        # Reuse your existing weather API key
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={config.BENGALURU_COORDS[0]}&lon={config.BENGALURU_COORDS[1]}"
            f"&appid={config.OPENWEATHER_API_KEY}&units=metric"
        )
        resp = requests.get(url, timeout=8)
        data = resp.json()

        wind_speed_ms  = data.get("wind", {}).get("speed", 5)       # m/s
        wind_speed_kmh = round(wind_speed_ms * 3.6, 1)
        wind_deg       = data.get("wind", {}).get("deg", 45)        # degrees
        humidity       = data.get("main", {}).get("humidity", 50)
        temp           = data.get("main", {}).get("temp", 28)
        weather_desc   = data.get("weather", [{}])[0].get("description", "clear sky")

        # Estimate fuel moisture from humidity + temperature
        # Dry + hot = low fuel moisture (dangerous), Humid = high (safer)
        fuel_moisture = round(max(5, min(40, humidity * 0.3 - temp * 0.2 + 15)), 1)

        # Fire danger rating (like FWI — simplified)
        danger_score = max(0, min(100, (100 - humidity) * 0.4 + wind_speed_kmh * 0.4 + (temp - 20) * 0.5))
        if danger_score >= 80:   fire_danger = "EXTREME"
        elif danger_score >= 60: fire_danger = "HIGH"
        elif danger_score >= 40: fire_danger = "MODERATE"
        else:                    fire_danger = "LOW"

        return jsonify({
            "status":        "live",
            "wind_speed_kmh": wind_speed_kmh,
            "wind_direction": wind_deg,
            "humidity":       humidity,
            "temperature":    temp,
            "fuel_moisture":  fuel_moisture,
            "weather_desc":   weather_desc,
            "fire_danger":    fire_danger,
            "danger_score":   round(danger_score, 1),
            "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    except Exception as e:
        # Fallback to simulated data if API fails
        return jsonify({
            "status":         "simulated",
            "wind_speed_kmh": 22,
            "wind_direction": 45,
            "humidity":       42,
            "temperature":    29,
            "fuel_moisture":  12,
            "weather_desc":   "partly cloudy",
            "fire_danger":    "MODERATE",
            "danger_score":   48.0,
            "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note":           f"Live API unavailable: {str(e)}",
        })


# ── API: Fire economic impact calculator ────────────────────────────
@app.route("/api/fire/economic-impact", methods=["POST"])
def fire_economic_impact():
    """
    Given simulation results (cells burned, zone info),
    calculate detailed economic impact breakdown.
    This is what makes the simulation "financially aware" — your
    senior's advice about quantifying cost/benefit.
    """
    data         = request.get_json()
    burned_cells = int(data.get("burned_cells", 0))
    active_cells = int(data.get("active_cells", 0))
    zone_name    = data.get("zone_name", "Electronic City")
    sim_minutes  = int(data.get("sim_minutes", 60))
    wind_speed   = float(data.get("wind_speed", 20))

    # Property value per cell (₹ Crore) — realistic Bengaluru figures
    ZONE_VALUES = {
        "Electronic City": {"residential": 9,  "industrial": 18, "commercial": 14},
        "Whitefield":      {"residential": 11, "industrial": 20, "commercial": 16},
        "Koramangala":     {"residential": 14, "industrial": 12, "commercial": 18},
        "Marathahalli":    {"residential": 8,  "industrial": 14, "commercial": 11},
        "Hebbal":          {"residential": 7,  "industrial": 11, "commercial": 10},
        "Bannerghatta":    {"residential": 5,  "industrial": 6,  "commercial": 7},
    }
    vals = ZONE_VALUES.get(zone_name, {"residential": 8, "industrial": 12, "commercial": 10})
    avg_val = (vals["residential"] * 0.4 + vals["industrial"] * 0.4 + vals["commercial"] * 0.2)

    # Direct losses
    prop_loss       = round(burned_cells * avg_val * 0.65, 1)    # 65% destruction assumed
    infra_loss      = round(burned_cells * 1.8, 1)               # roads, utilities, telecom
    business_loss   = round(burned_cells * avg_val * 0.3 + sim_minutes * 0.5, 1)  # lost revenue
    relief_cost     = round((burned_cells + active_cells) * 0.12 + sim_minutes * 0.04, 1)
    total_direct    = round(prop_loss + infra_loss + business_loss + relief_cost, 1)

    # Indirect losses (multiplier effect)
    indirect_loss   = round(total_direct * 0.35, 1)              # supply chain, workforce
    total_economic  = round(total_direct + indirect_loss, 1)

    # Savings from early warning (our system's value proposition)
    # Research shows early warning reduces losses by 30-40%
    early_warning_saves = round(total_economic * 0.35, 1)
    optimised_response  = round(relief_cost * 0.22, 1)           # LP optimization savings
    total_saves         = round(early_warning_saves + optimised_response, 1)

    # ROI of FloodSense Pro Fire Module
    # System annual cost estimate: ~₹12 lakh
    system_cost_cr = 0.12
    roi_x          = round(total_saves / system_cost_cr, 0) if total_saves > 0 else 0

    # Structures at risk
    avg_structures_per_cell = 45
    structures_at_risk      = (burned_cells + active_cells) * avg_structures_per_cell
    people_displaced        = round(structures_at_risk * 4.2)   # avg household size

    return jsonify({
        "breakdown": {
            "property_loss_cr":    prop_loss,
            "infrastructure_cr":   infra_loss,
            "business_loss_cr":    business_loss,
            "relief_cost_cr":      relief_cost,
            "total_direct_cr":     total_direct,
            "indirect_loss_cr":    indirect_loss,
            "total_economic_cr":   total_economic,
        },
        "early_warning_impact": {
            "loss_prevented_cr":    early_warning_saves,
            "optimization_saves_cr": optimised_response,
            "total_saves_cr":       total_saves,
            "system_cost_cr":       system_cost_cr,
            "roi_multiplier":       roi_x,
        },
        "human_impact": {
            "structures_at_risk":   structures_at_risk,
            "people_displaced":     people_displaced,
            "area_burned_km2":      round(burned_cells * 0.04, 2),
        },
        "risk_rating": (
            "CATASTROPHIC" if total_economic > 500 else
            "MAJOR"        if total_economic > 100 else
            "SIGNIFICANT"  if total_economic > 20  else
            "MODERATE"
        )
    })


# ── API: Fire spread risk zones (which Bengaluru zones are in path) ─
@app.route("/api/fire/zone-threat")
def fire_zone_threat():
    """
    Given a fire origin and wind direction, predict which
    Bengaluru zones are in the downwind threat corridor.
    Integrates with existing BENGALURU_ZONES from config.
    """
    import math

    origin_x  = float(request.args.get("origin_x", 42))
    origin_y  = float(request.args.get("origin_y", 44))
    wind_dir  = float(request.args.get("wind_dir", 45))
    wind_spd  = float(request.args.get("wind_spd", 24))
    step      = int(request.args.get("step", 0))

    # Map zone names to approximate grid positions
    ZONE_GRID = {
        "Bellandur":      (36, 40), "Marathahalli":  (42, 30),
        "HSR Layout":     (28, 42), "Whitefield":    (46, 20),
        "Koramangala":    (28, 34), "BTM Layout":    (24, 40),
        "Indiranagar":    (32, 24), "Hebbal":        (22, 12),
        "Yelahanka":      (20, 8),  "Electronic City":(42, 48),
    }

    wind_rad     = math.radians(wind_dir)
    spread_dist  = step * 0.8   # cells per step at given wind speed factor
    wind_factor  = wind_spd / 20.0

    threatened = []
    for zone_name, (zx, zy) in ZONE_GRID.items():
        dx = zx - origin_x
        dy = zy - origin_y
        dist = math.sqrt(dx*dx + dy*dy)

        # Angle from origin to zone
        angle_to_zone = math.degrees(math.atan2(dy, dx)) % 360
        angle_diff    = abs(angle_to_zone - wind_dir) % 360
        if angle_diff > 180:
            angle_diff = 360 - angle_diff

        # Zone is threatened if:
        # 1. In the downwind cone (within 60° of wind direction)
        # 2. Close enough given current spread
        in_cone    = angle_diff < 60
        reachable  = dist < (spread_dist * wind_factor + 5)
        threat_pct = max(0, min(100, (1 - dist/40) * 100 * (1 if in_cone else 0.2)))

        if threat_pct > 5:
            threatened.append({
                "zone":       zone_name,
                "threat_pct": round(threat_pct, 0),
                "distance":   round(dist * 0.2, 1),  # convert to km
                "in_cone":    in_cone,
                "status": (
                    "BURNING"    if threat_pct > 80 else
                    "THREATENED" if threat_pct > 50 else
                    "AT RISK"    if threat_pct > 20 else
                    "MONITOR"
                )
            })

    threatened.sort(key=lambda x: x["threat_pct"], reverse=True)
    return jsonify({"zones": threatened, "total_threatened": len(threatened)})
# ─── RUN ──────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs("database", exist_ok=True)
    print("\n" + "=" * 50)
    print("  FloodSense Pro — Starting Server")
    print("  Citizen Dashboard : http://127.0.0.1:5000/citizen")
    print("  Authority Dashboard: http://127.0.0.1:5000/authority")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000)