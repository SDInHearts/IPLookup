import os
import csv
import ipaddress
import requests
import maxminddb
import psycopg2

MMDB_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-City.mmdb"
MMDB_FILE = "GeoLite2-City.mmdb"
CSV_FILE = "data/GeoLite2-City.csv"
DB_URL = os.getenv("SUPABASE_DB_URL")

def download_mmdb():
    print("Downloading GeoLite2-City.mmdb...")
    response = requests.get(MMDB_URL, stream=True)
    response.raise_for_status()
    with open(MMDB_FILE, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print("Download complete.")

def convert_to_csv():
    print("Converting MMDB to CSV format...")
    os.makedirs("data", exist_ok=True)
    reader = maxminddb.open_database(MMDB_FILE)
    
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ip_start", "ip_end", "city", "region", "county", "country_name"])
        
        for network, data in reader:
            if not isinstance(data, dict):
                continue
            net = ipaddress.ip_network(network)
            if net.version == 4:
                ip_start = int(net.network_address)
                ip_end = int(net.broadcast_address)
                
                city = data.get("city", {}).get("names", {}).get("en")
                subdivisions = data.get("subdivisions", [])
                region = subdivisions[0].get("names", {}).get("en") if subdivisions else None
                county = subdivisions[1].get("names", {}).get("en") if len(subdivisions) > 1 else region
                country = data.get("country", {}).get("names", {}).get("en")
                
                writer.writerow([ip_start, ip_end, city, region, county, country])
                
    reader.close()
    if os.path.exists(MMDB_FILE):
        os.remove(MMDB_FILE)
    print(f"Conversion finished: {CSV_FILE}")

def upload_to_supabase():
    if not DB_URL:
        print("Warning: SUPABASE_DB_URL not detected. Skipping database sync.")
        return

    print("Syncing CSV data to Supabase database...")
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    try:
        cursor.execute("TRUNCATE TABLE geoip_city;")
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            copy_sql = "COPY geoip_city(ip_start, ip_end, city, region, county, country_name) FROM STDIN WITH (FORMAT csv, HEADER true);"
            cursor.copy_expert(copy_sql, f)
            
        conn.commit()
        print("Supabase database sync completed successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error during database sync: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    download_mmdb()
    convert_to_csv()
    upload_to_supabase()
