"""Pull NYC Yellow Taxi 2023 data from Socrata API and load into Postgres."""
import requests
import pandas as pd
import psycopg2
import time

API_URL = "https://data.cityofnewyork.us/resource/4b4i-vvec.json"
BATCH_SIZE = 1000

OFFSETS = [0, 16000000, 33000000, 49000000]   

def fetch_batch(offset, limit):
    """Fetch one batch from the API at a given offset."""
    url = f"{API_URL}?$limit={limit}&$offset={offset}"
    print(f"  Fetching offset {offset:,}...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.json()

def main():
    print("Connecting to Postgres...")
    conn = psycopg2.connect(
        host="localhost", port=6544,
        user="taxi_user", password="taxi_pass",
        dbname="taxi"
    )
    cur = conn.cursor()

    # Recreate tables
    print("Creating tables...")
    cur.execute("""
        DROP TABLE IF EXISTS yellow_taxi_2023;
        CREATE TABLE yellow_taxi_2023 (
            id BIGSERIAL PRIMARY KEY,
            pickup_datetime TIMESTAMP,
            dropoff_datetime TIMESTAMP,
            trip_distance NUMERIC(10,2),
            passenger_count INTEGER,
            tip_amount NUMERIC(10,2),
            tolls_amount NUMERIC(10,2),
            improvement_surcharge NUMERIC(10,2),
            fare_amount NUMERIC(10,2),
            total_amount NUMERIC(10,2),
            payment_type VARCHAR(10),
            pickup_zone VARCHAR(10),
            dropoff_zone VARCHAR(10)
        );
    """)
    cur.execute("""
        DROP TABLE IF EXISTS taxi_zones;
        CREATE TABLE taxi_zones (
            zone_id VARCHAR(10) PRIMARY KEY,
            borough VARCHAR(20),
            zone_name VARCHAR(100)
        );
    """)
    conn.commit()

    # Load zone lookup table
    print("Loading zone lookup table...")
    zone_url = "https://data.cityofnewyork.us/resource/8meu-9t5y.json?$limit=500"   
    zone_data = requests.get(zone_url, timeout=60).json()
    zone_df = pd.DataFrame(zone_data)
    zone_df = zone_df.rename(columns={
        "locationid": "zone_id",
        "borough": "borough",
        "zone": "zone_name"
    })   
    zone_df = zone_df[["zone_id", "borough", "zone_name"]]
    cur.executemany(
        "INSERT INTO taxi_zones VALUES (%s, %s, %s) ON CONFLICT (zone_id) DO NOTHING",
        zone_df.values.tolist()
    )
    conn.commit()
    print(f"  Loaded {len(zone_df)} zones")

    # Fetch taxi data at different offsets
    total_fetched = 0
    for offset in OFFSETS:
        data = fetch_batch(offset, BATCH_SIZE)
        if not data:
            print(f"    No data at offset {offset}, skipping.")
            continue

        df = pd.DataFrame(data)
        df = df.rename(columns={
            "tpep_pickup_datetime": "pickup_datetime",
            "tpep_dropoff_datetime": "dropoff_datetime",
            "pulocationid": "pickup_zone",
            "dolocationid": "dropoff_zone",
        })

        # Convert numeric columns
        numeric_cols = ["trip_distance", "passenger_count", "tip_amount",
                        "tolls_amount", "improvement_surcharge", "fare_amount",
                        "total_amount"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Clean
        df["pickup_datetime"] = pd.to_datetime(df["pickup_datetime"])
        df["dropoff_datetime"] = pd.to_datetime(df["dropoff_datetime"])
        df = df.dropna(subset=["pickup_datetime", "fare_amount"])
        df = df[df["fare_amount"] > 0]

        # Select only the columns we need
        df = df[["pickup_datetime", "dropoff_datetime", "trip_distance",
                 "passenger_count", "tip_amount", "tolls_amount",
                 "improvement_surcharge", "fare_amount", "total_amount",
                 "payment_type", "pickup_zone", "dropoff_zone"]]

        records = df.values.tolist()
        cur.executemany("""
            INSERT INTO yellow_taxi_2023
            (pickup_datetime, dropoff_datetime, trip_distance, passenger_count,
             tip_amount, tolls_amount, improvement_surcharge, fare_amount,
             total_amount, payment_type, pickup_zone, dropoff_zone)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, records)
        conn.commit()
        total_fetched += len(records)
        print(f"    Loaded {len(records)} rows (total: {total_fetched})")
        time.sleep(1)

    cur.execute("SELECT COUNT(*) FROM yellow_taxi_2023;")
    count = cur.fetchone()[0]
    print(f"\nDone! {count} rows in yellow_taxi_2023")

    # Month distribution check
    cur.execute("""
        SELECT date_trunc('month', pickup_datetime) AS m, COUNT(*)
        FROM yellow_taxi_2023 GROUP BY 1 ORDER BY 1
    """)
    print("\nRows per month:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()   
