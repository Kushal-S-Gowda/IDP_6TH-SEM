# FloodSense Pro — Data Preprocessing & Synthetic Dataset Generator
# Generates realistic training data based on Indian flood patterns

import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
import joblib
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set random seed for reproducibility
np.random.seed(42)

def generate_flood_dataset(n_samples=5000):
    """
    Generates realistic synthetic flood dataset based on
    actual Indian flood patterns and meteorological relationships.
    """
    print("Generating flood dataset...")

    data = []

    for _ in range(n_samples):
        # ── Core weather features ──────────────────────────
        rainfall_24h = np.random.exponential(scale=20)       # mm, skewed right
        rainfall_24h = min(rainfall_24h, 300)                 # cap at 300mm

        rainfall_7d = rainfall_24h * np.random.uniform(3, 8) # 7-day accumulation
        rainfall_7d = min(rainfall_7d, 800)

        temperature = np.random.normal(28, 6)                 # Indian avg temp
        humidity = np.random.uniform(40, 100)
        wind_speed = np.random.exponential(scale=15)
        wind_speed = min(wind_speed, 120)

        # ── Geographical features ──────────────────────────
        elevation = np.random.exponential(scale=200)          # meters
        elevation = max(10, min(elevation, 1500))             # 10m to 1500m

        river_proximity = np.random.exponential(scale=5)      # km
        river_proximity = max(0.1, min(river_proximity, 50))

        # ── Historical and soil features ───────────────────
        flood_history_freq = np.random.beta(2, 5)             # 0 to 1
        soil_saturation_idx = min(1.0, rainfall_7d / 500)
        population_density = np.random.exponential(scale=3000)
        population_density = max(100, min(population_density, 50000))

        # ── Risk Label Calculation ─────────────────────────
        # Based on real flood meteorology principles
        risk_score = 0

        # Rainfall 24h contribution (most important)
        if rainfall_24h > 150:   risk_score += 4
        elif rainfall_24h > 80:  risk_score += 3
        elif rainfall_24h > 40:  risk_score += 2
        elif rainfall_24h > 15:  risk_score += 1

        # Rainfall 7-day accumulation
        if rainfall_7d > 400:    risk_score += 3
        elif rainfall_7d > 200:  risk_score += 2
        elif rainfall_7d > 80:   risk_score += 1

        # Elevation (lower = higher risk)
        if elevation < 30:       risk_score += 3
        elif elevation < 80:     risk_score += 2
        elif elevation < 200:    risk_score += 1

        # River proximity (closer = higher risk)
        if river_proximity < 0.5:  risk_score += 3
        elif river_proximity < 2:  risk_score += 2
        elif river_proximity < 5:  risk_score += 1

        # Soil saturation
        if soil_saturation_idx > 0.8:  risk_score += 2
        elif soil_saturation_idx > 0.5: risk_score += 1

        # Historical frequency
        if flood_history_freq > 0.7:   risk_score += 2
        elif flood_history_freq > 0.4: risk_score += 1

        # Humidity amplifier
        if humidity > 85 and rainfall_24h > 20: risk_score += 1

        # Add small random noise
        risk_score += np.random.randint(-1, 2)
        risk_score = max(0, risk_score)

        # Convert score to risk class
        if risk_score >= 12:     risk_level = 3  # EXTREME
        elif risk_score >= 8:    risk_level = 2  # HIGH
        elif risk_score >= 4:    risk_level = 1  # MEDIUM
        else:                    risk_level = 0  # LOW

        data.append({
            "rainfall_24h":        round(rainfall_24h, 2),
            "rainfall_7d":         round(rainfall_7d, 2),
            "temperature":         round(temperature, 1),
            "humidity":            round(humidity, 1),
            "wind_speed":          round(wind_speed, 1),
            "elevation":           round(elevation, 1),
            "river_proximity":     round(river_proximity, 2),
            "flood_history_freq":  round(flood_history_freq, 3),
            "soil_saturation_idx": round(soil_saturation_idx, 3),
            "population_density":  round(population_density, 0),
            "risk_level":          risk_level
        })

    df = pd.DataFrame(data)
    return df


def preprocess_and_split(df):
    """
    Scales features and splits into train/test sets.
    Saves scaler for use during live prediction.
    """
    print("Preprocessing data...")

    FEATURES = [
        "rainfall_24h", "rainfall_7d", "temperature",
        "humidity", "wind_speed", "elevation",
        "river_proximity", "flood_history_freq",
        "soil_saturation_idx", "population_density"
    ]

    X = df[FEATURES]
    y = df["risk_level"]

    # Scale features to 0-1 range
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    # Train/test split — stratified to keep class balance
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    # Save scaler — needed for live predictions later
    os.makedirs("ml/models", exist_ok=True)
    joblib.dump(scaler, "ml/models/scaler.pkl")
    print("  Scaler saved → ml/models/scaler.pkl")

    return X_train, X_test, y_train, y_test, scaler


def show_dataset_stats(df):
    """Print dataset summary statistics."""
    print("\n── Dataset Summary ─────────────────────────")
    print(f"  Total samples   : {len(df)}")
    print(f"  Features        : {len(df.columns) - 1}")
    print("\n  Risk Level Distribution:")
    labels = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "EXTREME"}
    for level, count in df["risk_level"].value_counts().sort_index().items():
        pct = count / len(df) * 100
        bar = "█" * int(pct / 2)
        print(f"    {labels[level]:8s} ({level}): {count:5d} samples ({pct:.1f}%) {bar}")
    print("─────────────────────────────────────────────")


# ─── TEST ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("FloodSense Pro — Data Preprocessing")
    print("=" * 45)

    # Generate dataset
    df = generate_flood_dataset(n_samples=5000)

    # Show stats
    show_dataset_stats(df)

    # Save raw dataset
    os.makedirs("data/processed", exist_ok=True)
    df.to_csv("data/processed/flood_dataset.csv", index=False)
    print("\n  Dataset saved → data/processed/flood_dataset.csv")

    # Preprocess and split
    X_train, X_test, y_train, y_test, scaler = preprocess_and_split(df)

    print(f"\n  Training set  : {X_train.shape[0]} samples")
    print(f"  Test set      : {X_test.shape[0]} samples")
    print(f"  Feature count : {X_train.shape[1]}")

    print("\n✅ Preprocessing complete!")