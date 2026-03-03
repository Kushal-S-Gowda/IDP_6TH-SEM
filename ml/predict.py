# FloodSense Pro — Live Prediction Module
# Loads trained model and predicts risk for any input

import joblib
import numpy as np
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Load model and scaler once at startup ────────────────────
MODEL_PATH  = "ml/models/best_model.pkl"
SCALER_PATH = "ml/models/scaler.pkl"

model  = joblib.load(MODEL_PATH)
scaler = joblib.load(SCALER_PATH)

RISK_LABELS = {
    0: {"label": "LOW",     "color": "green",  "hex": "#28a745", "action": "No immediate action required. Monitor conditions."},
    1: {"label": "MEDIUM",  "color": "yellow", "hex": "#ffc107", "action": "Elevated risk. Pre-position resources and issue advisory."},
    2: {"label": "HIGH",    "color": "orange", "hex": "#fd7e14", "action": "Flood likely within 24 hours. Begin evacuation of vulnerable areas."},
    3: {"label": "EXTREME", "color": "red",    "hex": "#dc3545", "action": "Imminent catastrophic flood. Activate full emergency protocol immediately."},
}

def predict_risk(
    rainfall_24h,
    rainfall_7d,
    temperature,
    humidity,
    wind_speed,
    elevation,
    river_proximity,
    flood_history_freq,
    soil_saturation_idx,
    population_density
):
    """
    Predict flood risk level for given conditions.
    Returns dict with risk level, label, color, score, and action.
    """
    features = np.array([[
        rainfall_24h,
        rainfall_7d,
        temperature,
        humidity,
        wind_speed,
        elevation,
        river_proximity,
        flood_history_freq,
        soil_saturation_idx,
        population_density
    ]])

    # Scale features using saved scaler
    features_scaled = scaler.transform(features)

    # Predict class and probability
    risk_class = int(model.predict(features_scaled)[0])
    probabilities = model.predict_proba(features_scaled)[0]
    risk_score = round(float(probabilities[risk_class]) * 100, 1)

    # All class probabilities as percentages
    all_probs = {
        RISK_LABELS[i]["label"]: round(float(p) * 100, 1)
        for i, p in enumerate(probabilities)
    }

    result = {
        "risk_class":    risk_class,
        "risk_label":    RISK_LABELS[risk_class]["label"],
        "risk_color":    RISK_LABELS[risk_class]["color"],
        "risk_hex":      RISK_LABELS[risk_class]["hex"],
        "risk_score":    risk_score,
        "action":        RISK_LABELS[risk_class]["action"],
        "probabilities": all_probs
    }
    return result


def predict_risk_from_weather(weather_data, zone_data):
    """
    Predict risk using live weather API data + zone geographical data.
    weather_data: dict from api/weather.py get_current_weather()
    zone_data: dict with elevation, river_proximity, flood_history_freq, population_density
    """
    rainfall_24h        = weather_data.get("rainfall_1h", 0) * 24
    rainfall_7d         = rainfall_24h * 5  # Estimate — real system uses IMD historical
    temperature         = weather_data.get("temperature", 28)
    humidity            = weather_data.get("humidity", 70)
    wind_speed          = weather_data.get("wind_speed", 10)
    elevation           = zone_data.get("elevation", 500)
    river_proximity     = zone_data.get("river_proximity", 5)
    flood_history_freq  = zone_data.get("flood_history", 0.3)
    soil_saturation_idx = min(1.0, rainfall_7d / 500)
    population_density  = zone_data.get("population", 10000)

    return predict_risk(
        rainfall_24h, rainfall_7d, temperature, humidity,
        wind_speed, elevation, river_proximity,
        flood_history_freq, soil_saturation_idx, population_density
    )


def predict_all_zones(zones_with_weather):
    """
    Predict risk for all Bengaluru zones at once.
    Used by authority dashboard map.
    """
    results = []
    for zone in zones_with_weather:
        prediction = predict_risk_from_weather(zone, zone)
        results.append({**zone, **prediction})
    return results


# ─── TEST ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("FloodSense Pro — Prediction Module Test")
    print("=" * 50)

    # Test 1: Normal day — LOW risk
    print("\n[TEST 1] Normal day in Bengaluru:")
    r = predict_risk(
        rainfall_24h=5, rainfall_7d=20, temperature=30,
        humidity=60, wind_speed=10, elevation=920,
        river_proximity=5, flood_history_freq=0.2,
        soil_saturation_idx=0.04, population_density=8000
    )
    print(f"  Risk Level : {r['risk_label']} ({r['risk_color'].upper()})")
    print(f"  Confidence : {r['risk_score']}%")
    print(f"  Action     : {r['action']}")

    # Test 2: Monsoon scenario — HIGH risk
    print("\n[TEST 2] Heavy monsoon scenario:")
    r = predict_risk(
        rainfall_24h=95, rainfall_7d=380, temperature=24,
        humidity=95, wind_speed=45, elevation=887,
        river_proximity=0.5, flood_history_freq=0.9,
        soil_saturation_idx=0.76, population_density=45000
    )
    print(f"  Risk Level : {r['risk_label']} ({r['risk_color'].upper()})")
    print(f"  Confidence : {r['risk_score']}%")
    print(f"  Action     : {r['action']}")
    print(f"  Probabilities: {r['probabilities']}")

    # Test 3: Extreme flood scenario
    print("\n[TEST 3] Extreme flood scenario (Kerala 2018-like):")
    r = predict_risk(
        rainfall_24h=180, rainfall_7d=650, temperature=22,
        humidity=99, wind_speed=75, elevation=30,
        river_proximity=0.2, flood_history_freq=0.95,
        soil_saturation_idx=0.99, population_density=35000
    )
    print(f"  Risk Level : {r['risk_label']} ({r['risk_color'].upper()})")
    print(f"  Confidence : {r['risk_score']}%")
    print(f"  Action     : {r['action']}")

    print("\n✅ Prediction module ready!")