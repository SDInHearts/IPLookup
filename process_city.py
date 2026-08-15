import os
import io
import csv
import ipaddress
import requests
import maxminddb
import psycopg2

MMDB_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
MMDB_FILE = "GeoLite2-Country.mmdb"
DB_URL = os.getenv("SUPABASE_DB_URL")

def download_mmdb():
    print("Downloading GeoLite2-Country.mmdb...")
    response = requests.get(MMDB_URL, stream=True)
    response.raise_for_status()
    with open(MMDB_FILE, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print("Download complete.")

def process_and_upload():
    if not DB_URL:
        print("Warning: SUPABASE_DB_URL not detected. Skipping database sync.")
        return

    print("Processing GeoLite2-Country MMDB in memory...")
    reader = maxminddb.open_database(MMDB_FILE)
    
    # In-memory CSV buffer to avoid writing CSV to disk
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    
    for network, data in reader:
        if not isinstance(data, dict):
            continue
        net = ipaddress.ip_network(network)
        if net.version == 4:
            ip_start = int(net.network_address)
            ip_end = int(net.broadcast_address)
            
            country_data = data.get("country", {})
            continent_data = data.get("continent", {})
            
            country_code = country_data.get("iso_code")
            country_name = country_data.get("names", {}).get("en")
            continent_code = continent_data.get("code")
            
            writer.writerow([ip_start, ip_end, country_code, country_name, continent_code])
            
    reader.close()
    
    # Remove local temp mmdb file after parsing
    if os.path.exists(MMDB_FILE):
        os.remove(MMDB_FILE)
        
    csv_buffer.seek(0)
    
    print("Syncing directly to Supabase database...")
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    try:
        cursor.execute("TRUNCATE TABLE geoip_country;")
        copy_sql = """
            COPY geoip_country(ip_start, ip_end, country_code, country_name, continent_code) 
            FROM STDIN WITH (FORMAT csv);
        """
        cursor.copy_expert(copy_sql, csv_buffer)
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
    process_and_upload()
