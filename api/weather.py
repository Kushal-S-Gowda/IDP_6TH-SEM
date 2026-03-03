# FloodSense Pro — Weather API Module
# Fetches live weather data from OpenWeatherMap

import requests
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

BASE_URL = "http://api.openweathermap.org/data/2.5"

def get_current_weather(city_name):
    """
    Fetch current weather for a city.
    Returns dict with rainfall, temperature, humidity, wind speed.
    """
    try:
        url = f"{BASE_URL}/weather"
        params = {
            "q": f"{city_name},IN",  # IN = India
            "appid": config.OPENWEATHER_API_KEY,
            "units": "metric"  # Celsius
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Extract rainfall (may not exist if no rain)
        rainfall_1h = data.get("rain", {}).get("1h", 0.0)
        rainfall_3h = data.get("rain", {}).get("3h", 0.0)

        result = {
            "city": data["name"],
            "country": data["sys"]["country"],
            "temperature": round(data["main"]["temp"], 1),
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "wind_speed": round(data["wind"]["speed"] * 3.6, 1),  # m/s to km/h
            "rainfall_1h": round(rainfall_1h, 2),
            "rainfall_3h": round(rainfall_3h, 2),
            "weather_desc": data["weather"][0]["description"].title(),
            "lat": data["coord"]["lat"],
            "lon": data["coord"]["lon"],
            "status": "success"
        }
        return result

    except requests.exceptions.HTTPError as e:
        return {"status": "error", "message": f"City not found: {city_name}"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "message": "No internet connection"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_forecast(city_name):
    """
    Fetch 5-day / 3-hour forecast for a city.
    Returns list of forecast entries with rainfall predictions.
    """
    try:
        url = f"{BASE_URL}/forecast"
        params = {
            "q": f"{city_name},IN",
            "appid": config.OPENWEATHER_API_KEY,
            "units": "metric",
            "cnt": 16  # 16 entries = 48 hours (every 3 hours)
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        forecast_list = []
        for entry in data["list"]:
            rainfall = entry.get("rain", {}).get("3h", 0.0)
            forecast_list.append({
                "datetime": entry["dt_txt"],
                "temperature": round(entry["main"]["temp"], 1),
                "humidity": entry["main"]["humidity"],
                "rainfall_3h": round(rainfall, 2),
                "wind_speed": round(entry["wind"]["speed"] * 3.6, 1),
                "description": entry["weather"][0]["description"].title()
            })

        return {"status": "success", "city": city_name, "forecast": forecast_list}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_weather_for_zones(zones):
    """
    Fetch weather for multiple zones using coordinates.
    Used for the authority dashboard map.
    """
    results = []
    for zone in zones:
        try:
            url = f"{BASE_URL}/weather"
            params = {
                "lat": zone["lat"],
                "lon": zone["lon"],
                "appid": config.OPENWEATHER_API_KEY,
                "units": "metric"
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            rainfall = data.get("rain", {}).get("1h", 0.0)
            zone_weather = {
                **zone,  # Keep all original zone data
                "temperature": round(data["main"]["temp"], 1),
                "humidity": data["main"]["humidity"],
                "rainfall_1h": round(rainfall, 2),
                "wind_speed": round(data["wind"]["speed"] * 3.6, 1),
                "weather_desc": data["weather"][0]["description"].title()
            }
            results.append(zone_weather)

        except Exception as e:
            # If API fails for one zone, use defaults
            results.append({
                **zone,
                "temperature": 25.0,
                "humidity": 70,
                "rainfall_1h": 0.0,
                "wind_speed": 10.0,
                "weather_desc": "Data unavailable"
            })

    return results


# ─── TEST — Run this file directly to verify API works ───────
if __name__ == "__main__":
    print("Testing OpenWeatherMap API...")
    print("=" * 50)

    # Test 1: Current weather
    print("\n[TEST 1] Current weather for Bengaluru:")
    result = get_current_weather("Bengaluru")
    if result["status"] == "success":
        print(f"  City       : {result['city']}")
        print(f"  Temperature: {result['temperature']}°C")
        print(f"  Humidity   : {result['humidity']}%")
        print(f"  Rainfall   : {result['rainfall_1h']} mm/hr")
        print(f"  Wind Speed : {result['wind_speed']} km/h")
        print(f"  Condition  : {result['weather_desc']}")
        print("  ✅ Current weather API working!")
    else:
        print(f"  ❌ Error: {result['message']}")

    # Test 2: Forecast
    print("\n[TEST 2] 48-hour forecast for Bengaluru:")
    forecast = get_forecast("Bengaluru")
    if forecast["status"] == "success":
        print(f"  Got {len(forecast['forecast'])} forecast entries")
        print(f"  First entry: {forecast['forecast'][0]['datetime']}")
        print(f"  Rainfall predicted: {forecast['forecast'][0]['rainfall_3h']} mm")
        print("  ✅ Forecast API working!")
    else:
        print(f"  ❌ Error: {forecast['message']}")

    print("\n" + "=" * 50)
    print("API Module ready ✅")