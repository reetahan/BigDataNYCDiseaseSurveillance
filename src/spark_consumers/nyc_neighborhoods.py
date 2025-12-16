"""
NYC Neighborhood and Borough Mapping
Ticket 3.3: Location extraction and neighborhood assignment

Provides comprehensive mapping of NYC neighborhoods with approximate boundaries
"""

# NYC Borough boundaries (approximate centers and zip code ranges)
NYC_BOROUGHS = {
    "Manhattan": {
        "zip_ranges": ["100", "101", "102"],
        "center_lat": 40.7831,
        "center_lon": -73.9712
    },
    "Brooklyn": {
        "zip_ranges": ["112"],
        "center_lat": 40.6782,
        "center_lon": -73.9442
    },
    "Queens": {
        "zip_ranges": ["110", "111", "113", "114", "116"],
        "center_lat": 40.7282,
        "center_lon": -73.7949
    },
    "Bronx": {
        "zip_ranges": ["104"],
        "center_lat": 40.8448,
        "center_lon": -73.8648
    },
    "Staten Island": {
        "zip_ranges": ["103"],
        "center_lat": 40.5795,
        "center_lon": -74.1502
    }
}

# Manhattan neighborhoods with approximate boundaries
MANHATTAN_NEIGHBORHOODS = {
    "Upper East Side": {"lat_range": (40.76, 40.79), "lon_range": (-73.97, -73.94), "zips": ["10021", "10028", "10075", "10128"]},
    "Upper West Side": {"lat_range": (40.77, 40.80), "lon_range": (-73.99, -73.96), "zips": ["10023", "10024", "10025"]},
    "Harlem": {"lat_range": (40.80, 40.85), "lon_range": (-73.95, -73.93), "zips": ["10026", "10027", "10030", "10037", "10039"]},
    "East Harlem": {"lat_range": (40.79, 40.81), "lon_range": (-73.95, -73.92), "zips": ["10029", "10035"]},
    "Washington Heights": {"lat_range": (40.83, 40.86), "lon_range": (-73.94, -73.92), "zips": ["10032", "10033", "10040"]},
    "Inwood": {"lat_range": (40.86, 40.88), "lon_range": (-73.93, -73.90), "zips": ["10034"]},
    "Midtown": {"lat_range": (40.75, 40.77), "lon_range": (-73.99, -73.97), "zips": ["10018", "10019", "10020", "10022", "10036"]},
    "Chelsea": {"lat_range": (40.74, 40.76), "lon_range": (-74.01, -73.99), "zips": ["10001", "10011"]},
    "Greenwich Village": {"lat_range": (40.73, 40.74), "lon_range": (-74.01, -73.99), "zips": ["10003", "10012", "10014"]},
    "East Village": {"lat_range": (40.72, 40.73), "lon_range": (-73.99, -73.97), "zips": ["10003", "10009"]},
    "Lower East Side": {"lat_range": (40.71, 40.73), "lon_range": (-73.99, -73.97), "zips": ["10002"]},
    "Chinatown": {"lat_range": (40.71, 40.72), "lon_range": (-74.00, -73.99), "zips": ["10013"]},
    "SoHo": {"lat_range": (40.72, 40.73), "lon_range": (-74.01, -74.00), "zips": ["10012", "10013"]},
    "TriBeCa": {"lat_range": (40.71, 40.72), "lon_range": (-74.02, -74.01), "zips": ["10007", "10013"]},
    "Financial District": {"lat_range": (40.70, 40.71), "lon_range": (-74.02, -74.00), "zips": ["10004", "10005", "10006", "10038"]},
    "Battery Park City": {"lat_range": (40.70, 40.72), "lon_range": (-74.02, -74.01), "zips": ["10280", "10282"]},
}

# Brooklyn neighborhoods
BROOKLYN_NEIGHBORHOODS = {
    "Williamsburg": {"lat_range": (40.70, 40.72), "lon_range": (-73.97, -73.94), "zips": ["11211", "11249"]},
    "Greenpoint": {"lat_range": (40.72, 40.74), "lon_range": (-73.96, -73.93), "zips": ["11222"]},
    "Bushwick": {"lat_range": (40.69, 40.71), "lon_range": (-73.94, -73.91), "zips": ["11206", "11221", "11237"]},
    "Bedford-Stuyvesant": {"lat_range": (40.67, 40.69), "lon_range": (-73.96, -73.93), "zips": ["11216", "11221", "11233"]},
    "Park Slope": {"lat_range": (40.66, 40.68), "lon_range": (-73.99, -73.96), "zips": ["11215", "11217"]},
    "Prospect Heights": {"lat_range": (40.67, 40.68), "lon_range": (-73.97, -73.95), "zips": ["11238"]},
    "Crown Heights": {"lat_range": (40.65, 40.68), "lon_range": (-73.95, -73.92), "zips": ["11213", "11225", "11238"]},
    "Flatbush": {"lat_range": (40.63, 40.66), "lon_range": (-73.96, -73.93), "zips": ["11203", "11226"]},
    "Sunset Park": {"lat_range": (40.64, 40.66), "lon_range": (-74.02, -73.98), "zips": ["11220", "11232"]},
    "Bay Ridge": {"lat_range": (40.61, 40.64), "lon_range": (-74.04, -74.01), "zips": ["11209"]},
    "Brighton Beach": {"lat_range": (40.57, 40.58), "lon_range": (-73.97, -73.95), "zips": ["11235"]},
    "Coney Island": {"lat_range": (40.57, 40.58), "lon_range": (-73.99, -73.97), "zips": ["11224"]},
    "Downtown Brooklyn": {"lat_range": (40.69, 40.70), "lon_range": (-73.99, -73.97), "zips": ["11201", "11217"]},
}

# Queens neighborhoods
QUEENS_NEIGHBORHOODS = {
    "Astoria": {"lat_range": (40.76, 40.78), "lon_range": (-73.94, -73.91), "zips": ["11102", "11103", "11105", "11106"]},
    "Long Island City": {"lat_range": (40.74, 40.76), "lon_range": (-73.96, -73.93), "zips": ["11101", "11109"]},
    "Flushing": {"lat_range": (40.75, 40.77), "lon_range": (-73.84, -73.81), "zips": ["11354", "11355", "11358"]},
    "Jackson Heights": {"lat_range": (40.75, 40.76), "lon_range": (-73.89, -73.87), "zips": ["11372"]},
    "Elmhurst": {"lat_range": (40.73, 40.75), "lon_range": (-73.88, -73.86), "zips": ["11373"]},
    "Forest Hills": {"lat_range": (40.71, 40.73), "lon_range": (-73.85, -73.83), "zips": ["11375"]},
    "Jamaica": {"lat_range": (40.69, 40.71), "lon_range": (-73.81, -73.78), "zips": ["11432", "11433", "11434", "11435", "11436"]},
    "Rockaway": {"lat_range": (40.58, 40.60), "lon_range": (-73.84, -73.75), "zips": ["11691", "11692", "11693", "11694", "11697"]},
}

# Bronx neighborhoods
BRONX_NEIGHBORHOODS = {
    "Riverdale": {"lat_range": (40.88, 40.91), "lon_range": (-73.92, -73.89), "zips": ["10463", "10471"]},
    "Kingsbridge": {"lat_range": (40.87, 40.89), "lon_range": (-73.91, -73.89), "zips": ["10463", "10468"]},
    "Fordham": {"lat_range": (40.85, 40.88), "lon_range": (-73.91, -73.86), "zips": ["10458", "10468", "10467"]},
    "Belmont": {"lat_range": (40.85, 40.86), "lon_range": (-73.89, -73.87), "zips": ["10458"]},
    "Morris Park": {"lat_range": (40.84, 40.86), "lon_range": (-73.86, -73.84), "zips": ["10461", "10462"]},
    "Pelham Bay": {"lat_range": (40.85, 40.87), "lon_range": (-73.83, -73.80), "zips": ["10461", "10464", "10465"]},
    "Hunts Point": {"lat_range": (40.81, 40.82), "lon_range": (-73.89, -73.87), "zips": ["10474"]},
    "Mott Haven": {"lat_range": (40.80, 40.82), "lon_range": (-73.93, -73.91), "zips": ["10451", "10454"]},
    "Concourse": {"lat_range": (40.83, 40.85), "lon_range": (-73.92, -73.90), "zips": ["10451", "10452", "10456"]},
    "Tremont": {"lat_range": (40.84, 40.86), "lon_range": (-73.90, -73.88), "zips": ["10457"]},
    "Soundview": {"lat_range": (40.81, 40.83), "lon_range": (-73.87, -73.85), "zips": ["10472", "10473"]},
    "Throgs Neck": {"lat_range": (40.81, 40.83), "lon_range": (-73.83, -73.80), "zips": ["10465"]},
    "Co-op City": {"lat_range": (40.87, 40.88), "lon_range": (-73.83, -73.81), "zips": ["10475"]},
}

# Staten Island neighborhoods
STATEN_ISLAND_NEIGHBORHOODS = {
    "St. George": {"lat_range": (40.64, 40.65), "lon_range": (-74.08, -74.07), "zips": ["10301"]},
    "Stapleton": {"lat_range": (40.62, 40.63), "lon_range": (-74.08, -74.07), "zips": ["10304"]},
    "Tottenville": {"lat_range": (40.50, 40.52), "lon_range": (-74.25, -74.23), "zips": ["10307"]},
    "New Dorp": {"lat_range": (40.57, 40.58), "lon_range": (-74.12, -74.10), "zips": ["10306"]},
}

# Combine all neighborhoods
ALL_NEIGHBORHOODS = {
    **MANHATTAN_NEIGHBORHOODS,
    **BROOKLYN_NEIGHBORHOODS,
    **QUEENS_NEIGHBORHOODS,
    **BRONX_NEIGHBORHOODS,
    **STATEN_ISLAND_NEIGHBORHOODS
}

# Common NYC location aliases and landmarks
NYC_LOCATION_ALIASES = {
    # Boroughs
    "manhattan": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "Bronx",
    "the bronx": "Bronx",
    "staten island": "Staten Island",

    # Neighborhood aliases
    "upper east": "Upper East Side",
    "ues": "Upper East Side",
    "upper west": "Upper West Side",
    "uws": "Upper West Side",
    "downtown": "Downtown Brooklyn",
    "dumbo": "Downtown Brooklyn",
    "bushwick": "Bushwick",
    "bed stuy": "Bedford-Stuyvesant",
    "bedstuy": "Bedford-Stuyvesant",
    "bed-stuy": "Bedford-Stuyvesant",
    "park slope": "Park Slope",
    "williamsburg": "Williamsburg",
    "greenpoint": "Greenpoint",
    "crown heights": "Crown Heights",
    "prospect heights": "Prospect Heights",
    "flatbush": "Flatbush",
    "east village": "East Village",
    "west village": "Greenwich Village",
    "village": "Greenwich Village",
    "soho": "SoHo",
    "tribeca": "TriBeCa",
    "fidi": "Financial District",
    "lic": "Long Island City",
    "astoria": "Astoria",
    "flushing": "Flushing",

    # Landmarks
    "central park": "Midtown",
    "times square": "Midtown",
    "penn station": "Midtown",
    "grand central": "Midtown",
    "wall street": "Financial District",
    "world trade center": "Financial District",
    "wtc": "Financial District",
    "jfk": "Jamaica",
    "laguardia": "Jackson Heights",
    "yankee stadium": "Concourse",
    "citi field": "Flushing",
    "barclays center": "Prospect Heights",
    "prospect park": "Park Slope",
    "coney island": "Coney Island",
    "brighton beach": "Brighton Beach",
}


def get_borough_from_zip(zip_code: str) -> str:
    """Get borough from zip code"""
    if not zip_code or len(zip_code) < 3:
        return None

    zip_prefix = zip_code[:3]

    for borough, info in NYC_BOROUGHS.items():
        if zip_prefix in info["zip_ranges"]:
            return borough

    return None


def get_neighborhood_from_coords(lat: float, lon: float) -> str:
    """Get neighborhood from latitude/longitude coordinates"""
    if not lat or not lon:
        return None

    lat = float(lat)
    lon = float(lon)

    for neighborhood, bounds in ALL_NEIGHBORHOODS.items():
        lat_min, lat_max = bounds["lat_range"]
        lon_min, lon_max = bounds["lon_range"]

        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return neighborhood

    return None


def get_neighborhood_from_zip(zip_code: str) -> str:
    """Get neighborhood from zip code"""
    if not zip_code:
        return None

    for neighborhood, info in ALL_NEIGHBORHOODS.items():
        if zip_code in info["zips"]:
            return neighborhood

    return None


def normalize_location_name(location_text: str) -> str:
    """Normalize location name using aliases"""
    if not location_text:
        return None

    location_lower = location_text.lower().strip()

    # Check aliases first
    if location_lower in NYC_LOCATION_ALIASES:
        return NYC_LOCATION_ALIASES[location_lower]

    # Check direct neighborhood matches
    for neighborhood in ALL_NEIGHBORHOODS.keys():
        if neighborhood.lower() == location_lower:
            return neighborhood

    # Check borough matches
    for borough in NYC_BOROUGHS.keys():
        if borough.lower() == location_lower:
            return borough

    return None
