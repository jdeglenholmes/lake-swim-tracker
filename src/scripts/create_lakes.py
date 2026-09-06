import requests
import time
import json
import os

# Complete configuration map of all lakes and their target lengths in metres
LAKES_CONFIG = {
    "Windermere": 17000, 
    "Ullswater": 11800, 
    "Derwent Water": 4600,       # Updated: OSM uses a space
    "Bassenthwaite Lake": 6400, 
    "Coniston Water": 8000,
    "Thirlmere": 5600,
    "Ennerdale Water": 3900,
    "Wast Water": 4800, 
    "Crummock Water": 4000
}

def get_lake_svg_path(lake_name, max_retries=4):
    overpass_url = "http://overpass-api.de/api/interpreter"
    bbox = "54.2,-3.5,54.8,-2.7"
    
    overpass_query = f"""
    [out:json][timeout:25];
    (
      relation["name"="{lake_name}"]["natural"="water"]({bbox});
      way["name"="{lake_name}"]["natural"="water"]({bbox});
    );
    out geom;
    """
    
    # Added 'Accept' header to prevent HTTP 406 errors
    headers = {
        'User-Agent': 'LakeSwimTracker/1.2 (Contact: your_email@example.com)',
        'Accept': 'application/json'
    }
    
    data = None
    
    for attempt in range(max_retries):
        try:
            response = requests.post(overpass_url, data={'data': overpass_query}, headers=headers, timeout=30)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    break  # Success
                except requests.exceptions.JSONDecodeError:
                    return f"JSON Error. Raw response: {response.text[:100]}"
                    
            elif response.status_code in (429, 504):
                wait_time = (attempt + 1) * 5  # Exponential backoff
                print(f"[{lake_name}] HTTP {response.status_code}. Rate limited/timeout. Waiting {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                return f"HTTP Error {response.status_code}: {response.text[:100]}"
                
        except requests.exceptions.RequestException as e:
            print(f"[{lake_name}] Network error: {e}. Waiting 5s...")
            time.sleep(5)
    
    if not data:
        return f"Failed to retrieve data for {lake_name} after {max_retries} attempts."
        
    if not data.get('elements'):
        return f"Lake '{lake_name}' not found in OSM data."

    element = data['elements'][0]
    points = []
    
    if element['type'] == 'way':
        points = [(node['lon'], node['lat']) for node in element['geometry']]
    elif element['type'] == 'relation':
        for member in element.get('members', []):
            if member['role'] == 'outer' and 'geometry' in member:
                points.extend([(node['lon'], node['lat']) for node in member['geometry']])

    if not points:
        return "No geometry found."

    simplification_factor = max(1, len(points) // 20) 
    simplified_points = points[::simplification_factor]

    min_lon = min(p[0] for p in simplified_points)
    max_lon = max(p[0] for p in simplified_points)
    min_lat = min(p[1] for p in simplified_points)
    max_lat = max(p[1] for p in simplified_points)

    lon_range = max_lon - min_lon
    lat_range = max_lat - min_lat
    
    padding = 0.1 
    lon_range += lon_range * padding
    lat_range += lat_range * padding
    
    scale = 90 / max(lon_range, lat_range)

    svg_path = []
    for i, (lon, lat) in enumerate(simplified_points):
        x = 5 + (lon - min_lon) * scale
        y = 95 - (lat - min_lat) * scale 
        
        command = "M" if i == 0 else "L"
        svg_path.append(f"{command} {x:.1f} {y:.1f}")

    svg_path.append("Z")
    return " ".join(svg_path)

# --- INCREMENTAL RECOVERY LOGIC ---
filename = "lakes_data.json"
lakes_output = {}

# Load existing JSON if it already exists
if os.path.exists(filename):
    with open(filename, "r") as f:
        try:
            lakes_output = json.load(f)
            print(f"Loaded existing {filename} with {len(lakes_output)} entries.")
        except json.JSONDecodeError:
            print("Existing JSON was corrupted. Starting fresh.")

print("Checking for missing or corrupted lake entries...\n")

for lake, length in LAKES_CONFIG.items():
    existing_entry = lakes_output.get(lake)
    
    # Check if entry is completely missing OR contains an error string in the path
    is_missing = not existing_entry
    has_error = existing_entry and any(err in existing_entry.get("path", "") for err in ["HTTP Error", "not found", "Error", "Failed"])
    
    if is_missing or has_error:
        reason = "Missing" if is_missing else "Corrupted/Error path"
        print(f"-> Fetching '{lake}' ({reason})...")
        
        path_string = get_lake_svg_path(lake)
        
        lakes_output[lake] = {
            "length": length,
            "path": path_string
        }
        
        # Save incrementally after each fix
        with open(filename, "w") as f:
            json.dump(lakes_output, f, indent=4)
            
        time.sleep(3)  # Respectful delay between queries
    else:
        print(f"✓ Skipping '{lake}' (Already valid)")

print(f"\nAll checks complete! Updated data saved to {filename}.")