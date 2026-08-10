"""India-aware geography assets for the dashboard.

Plotly's built-in basemaps have two gaps this module closes:

1. The default world boundary draws India **without Jammu & Kashmir and Ladakh**.
   We ship a district-level GeoJSON that includes both, and render India from
   that instead of relying on the built-in outline.
2. There are no Indian state or district boundaries at all, and no way to fold
   "India" / "IND" / "IN" into a single country.

Everything here is plain Python + JSON - no geopandas/shapely needed. Results are
cached in-process, so the 4 MB GeoJSON is parsed once per app run.
"""

import json
import os
import re
from functools import lru_cache

import pycountry

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
DISTRICT_GEOJSON = os.path.join(ASSETS_DIR, "india_districts.geojson")

# Spellings that appear in real-world data but not in the official GeoJSON.
STATE_ALIASES = {
    "orissa": "Odisha",
    "pondicherry": "Puducherry",
    "pondichery": "Puducherry",
    "uttaranchal": "Uttarakhand",
    "nct of delhi": "Delhi",
    "new delhi": "Delhi",
    "delhi ncr": "Delhi",
    "ncr": "Delhi",
    "jk": "Jammu and Kashmir",
    "j and k": "Jammu and Kashmir",
    "jammu kashmir": "Jammu and Kashmir",
    "tamilnadu": "Tamil Nadu",
    "chattisgarh": "Chhattisgarh",
    "chhatisgarh": "Chhattisgarh",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "andaman nicobar": "Andaman and Nicobar Islands",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "telengana": "Telangana",
}

# Official 2-letter state codes. Real sheets are full of these ("MH", "DL", "KA").
# Note: in a *state* column "UK" means Uttarakhand, not the United Kingdom.
STATE_CODES = {
    "an": "Andaman and Nicobar Islands", "ap": "Andhra Pradesh",
    "ar": "Arunachal Pradesh", "as": "Assam", "br": "Bihar", "ch": "Chandigarh",
    "cg": "Chhattisgarh", "ct": "Chhattisgarh",
    "dn": "Dadra and Nagar Haveli and Daman and Diu",
    "dd": "Dadra and Nagar Haveli and Daman and Diu", "dl": "Delhi",
    "ga": "Goa", "gj": "Gujarat", "hr": "Haryana", "hp": "Himachal Pradesh",
    "jk": "Jammu and Kashmir", "jh": "Jharkhand", "ka": "Karnataka",
    "kl": "Kerala", "la": "Ladakh", "ld": "Lakshadweep", "mp": "Madhya Pradesh",
    "mh": "Maharashtra", "mn": "Manipur", "ml": "Meghalaya", "mz": "Mizoram",
    "nl": "Nagaland", "or": "Odisha", "od": "Odisha", "py": "Puducherry",
    "pb": "Punjab", "rj": "Rajasthan", "sk": "Sikkim", "tn": "Tamil Nadu",
    "ts": "Telangana", "tg": "Telangana", "tr": "Tripura", "up": "Uttar Pradesh",
    "uk": "Uttarakhand", "ut": "Uttarakhand", "wb": "West Bengal",
}

# Airport / IATA codes get used as city shorthand all the time in sales data.
CITY_CODES = {
    "del": "delhi", "bom": "mumbai", "blr": "bengaluru urban", "maa": "chennai",
    "ccu": "kolkata", "hyd": "hyderabad", "pnq": "pune", "amd": "ahmedabad",
    "lko": "lucknow", "jai": "jaipur", "goi": "north goa", "cok": "ernakulam",
    "ixc": "chandigarh", "pat": "patna", "ixr": "ranchi", "bho": "bhopal",
    "idr": "indore", "nag": "nagpur", "vns": "varanasi", "trv": "thiruvananthapuram",
    "gau": "kamrup metropolitan", "sxr": "srinagar", "ixj": "jammu",
    "atq": "amritsar", "stv": "surat", "vtz": "visakhapatnam", "cjb": "coimbatore",
    "ixm": "madurai", "rpr": "raipur", "jdh": "jodhpur", "udr": "udaipur",
    "ded": "dehradun", "knu": "kanpur nagar", "ixz": "nicobars",
}

# Popular city names that differ from the official district name in the GeoJSON.
CITY_ALIASES = {
    "bangalore": "bengaluru urban",
    "bengaluru": "bengaluru urban",
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "madras": "chennai",
    "mysore": "mysuru",
    "gurgaon": "gurugram",
    "noida": "gautam buddha nagar",
    "greater noida": "gautam buddha nagar",
    "kanpur": "kanpur nagar",
    "vizag": "visakhapatnam",
    "kochi": "ernakulam",
    "cochin": "ernakulam",
    "trivandrum": "thiruvananthapuram",
    "baroda": "vadodara",
    "allahabad": "prayagraj",
    "pondicherry": "puducherry",
    "new delhi": "delhi",
    "navi mumbai": "thane",
    "secunderabad": "hyderabad",
    "faridabad": "faridabad",
    "mangalore": "dakshina kannada",
    "hubli": "dharwad",
    "belgaum": "belagavi",
    "gulbarga": "kalaburagi",
    "bellary": "ballari",
    "tuticorin": "thoothukkudi",
    "trichy": "tiruchirappalli",
    "panjim": "north goa",
    "panaji": "north goa",
}

# Country spellings pycountry's strict lookup misses.
COUNTRY_ALIASES = {
    "bharat": "IND",
    "uk": "GBR",
    "u k": "GBR",
    "britain": "GBR",
    "great britain": "GBR",
    "england": "GBR",
    "uae": "ARE",
    "u a e": "ARE",
    "usa": "USA",
    "u s a": "USA",
    "us": "USA",
    "america": "USA",
    "south korea": "KOR",
    "north korea": "PRK",
    "russia": "RUS",
    "vietnam": "VNM",
    "iran": "IRN",
    "syria": "SYR",
    "laos": "LAO",
    "bolivia": "BOL",
    "venezuela": "VEN",
    "tanzania": "TZA",
    "moldova": "MDA",
    "czech republic": "CZE",
    "turkey": "TUR",
    "ivory coast": "CIV",
    "cape verde": "CPV",
    "swaziland": "SWZ",
    "burma": "MMR",
}


def norm_key(text):
    """Loose comparison key: lowercase, '&' -> 'and', punctuation stripped."""
    key = str(text).strip().lower().replace("&", " and ")
    key = re.sub(r"[^a-z0-9]+", " ", key)
    return re.sub(r"\s+", " ", key).strip()


# --------------------------------------------------------------------------- #
# GeoJSON loading and derived layers
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def load_district_geojson():
    """District-level India boundaries (includes J&K and Ladakh)."""
    if not os.path.exists(DISTRICT_GEOJSON):
        return None
    with open(DISTRICT_GEOJSON, encoding="utf-8") as handle:
        return json.load(handle)


def _iter_polygons(geometry):
    """Yield each polygon's coordinate list from a Polygon/MultiPolygon."""
    if not geometry:
        return
    if geometry.get("type") == "Polygon":
        yield geometry["coordinates"]
    elif geometry.get("type") == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            yield polygon


@lru_cache(maxsize=1)
def load_state_geojson():
    """State/UT boundaries, built by merging districts of the same state."""
    districts = load_district_geojson()
    if not districts:
        return None

    grouped = {}
    for feature in districts["features"]:
        state = feature["properties"].get("st_nm")
        if not state:
            continue
        grouped.setdefault(state, []).extend(_iter_polygons(feature["geometry"]))

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": state,
                "properties": {"st_nm": state},
                "geometry": {"type": "MultiPolygon", "coordinates": polygons},
            }
            for state, polygons in grouped.items()
        ],
    }


@lru_cache(maxsize=1)
def load_india_outline():
    """Whole of India as one feature - used to repaint India on the world map."""
    states = load_state_geojson()
    if not states:
        return None

    polygons = []
    for feature in states["features"]:
        polygons.extend(_iter_polygons(feature["geometry"]))

    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": "IND",
            "properties": {"iso3": "IND", "name": "India"},
            "geometry": {"type": "MultiPolygon", "coordinates": polygons},
        }],
    }


# --------------------------------------------------------------------------- #
# Name matching
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def state_lookup():
    """{normalized name: official state name}, aliases included."""
    states = load_state_geojson()
    if not states:
        return {}

    lookup = {norm_key(f["properties"]["st_nm"]): f["properties"]["st_nm"] for f in states["features"]}
    for alias, official in STATE_ALIASES.items():
        if norm_key(official) in lookup:
            lookup[norm_key(alias)] = official
    return lookup


@lru_cache(maxsize=1)
def district_lookup():
    """{normalized district name: (official district, state)}."""
    districts = load_district_geojson()
    if not districts:
        return {}

    lookup = {}
    for feature in districts["features"]:
        name = feature["properties"].get("district")
        if name:
            lookup.setdefault(norm_key(name), (name, feature["properties"].get("st_nm")))
    return lookup


def match_state(value):
    """Official Indian state/UT name for a raw label, or None.

    Accepts full names, common misspellings and the 2-letter codes ("MH", "DL")
    that real spreadsheets are full of.
    """
    key = norm_key(value)
    if not key:
        return None

    hit = state_lookup().get(key)
    if hit:
        return hit

    return STATE_CODES.get(key.replace(" ", ""))


def match_district(value):
    """Official Indian district name for a raw label, or None.

    Handles the everyday names people actually type - Bangalore, Gurgaon,
    Kochi - which differ from the official district in the boundary data.
    """
    lookup = district_lookup()
    key = norm_key(value)

    if key in lookup:
        return lookup[key][0]

    alias = CITY_ALIASES.get(key) or CITY_CODES.get(key.replace(" ", ""))
    if alias and alias in lookup:
        return lookup[alias][0]

    # "Pune City" / "Jaipur District" style values: fall back to a prefix match,
    # but only when it is unambiguous.
    if len(key) >= 4:
        candidates = [k for k in lookup if k.startswith(key)]
        if len(candidates) == 1:
            return lookup[candidates[0]][0]
        urban = [k for k in candidates if k.endswith("urban")]
        if len(urban) == 1:
            return lookup[urban[0]][0]

        # The other direction: "Pune City" / "Jaipur District" -> "Pune" / "Jaipur".
        head = key.split(" ")[0]
        if len(head) >= 4 and head in lookup:
            return lookup[head][0]

    return None


def normalize_country(value):
    """Fold any country spelling or code into one ISO-3 code.

    'India', 'IND', 'IN', 'india' all collapse to 'IND' - which is what stops the
    same country being counted three times on the map.
    """
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None

    key = norm_key(text)
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]

    try:
        return pycountry.countries.lookup(text).alpha_3
    except LookupError:
        pass

    # Last resort: match on the normalized official/common name.
    for country in pycountry.countries:
        for field in ("name", "official_name", "common_name"):
            candidate = getattr(country, field, None)
            if candidate and norm_key(candidate) == key:
                return country.alpha_3
    return None


def country_display_name(iso3):
    """Human-friendly country name for an ISO-3 code."""
    try:
        country = pycountry.countries.get(alpha_3=iso3)
        return getattr(country, "common_name", None) or country.name
    except (AttributeError, LookupError):
        return iso3


# --------------------------------------------------------------------------- #
# Centroids - so city/district names can be pinned without lat-long columns
# --------------------------------------------------------------------------- #

def _polygon_centroid(polygons):
    """Rough centre of the largest polygon - good enough to place a pin."""
    largest, best_size = None, -1
    for polygon in polygons:
        ring = polygon[0] if polygon else []
        if len(ring) > best_size:
            largest, best_size = ring, len(ring)

    if not largest:
        return None

    lons = [point[0] for point in largest]
    lats = [point[1] for point in largest]
    return sum(lats) / len(lats), sum(lons) / len(lons)


@lru_cache(maxsize=1)
def place_centroids():
    """{normalized place name: (lat, lon)} for every Indian state and district."""
    centroids = {}

    states = load_state_geojson()
    if states:
        for feature in states["features"]:
            point = _polygon_centroid(list(_iter_polygons(feature["geometry"])))
            if point:
                centroids[norm_key(feature["properties"]["st_nm"])] = point

    districts = load_district_geojson()
    if districts:
        for feature in districts["features"]:
            name = feature["properties"].get("district")
            if not name:
                continue
            key = norm_key(name)
            if key in centroids:
                continue
            point = _polygon_centroid(list(_iter_polygons(feature["geometry"])))
            if point:
                centroids[key] = point

    return centroids


def geocode_place(value):
    """(lat, lon) for an Indian city / district / state name, or None.

    Lets the app pin cities on a map even when the data has no Latitude and
    Longitude columns - the coordinates come from the bundled boundaries.
    """
    centroids = place_centroids()
    key = norm_key(value)

    if key in centroids:
        return centroids[key]

    official = match_state(value) or match_district(value)
    if official:
        return centroids.get(norm_key(official))

    return None
