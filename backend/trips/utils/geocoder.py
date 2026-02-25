import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode(location: str) -> dict:
    """
    Convert a location string to lat/lon using the Nominatim API.
    Returns {'lat': float, 'lon': float, 'display_name': str} or raises ValueError.
    """
    params = {
        "q": location,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": "DriverTripTrackerApp/1.0"}
    response = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    results = response.json()
    if not results:
        raise ValueError(f"Location not found: {location}")
    result = results[0]
    return {
        "lat": float(result["lat"]),
        "lon": float(result["lon"]),
        "display_name": result.get("display_name", location),
        "city": _extract_city(result.get("display_name", location)),
    }


def _extract_city(display_name: str) -> str:
    """Extract city and state/country from a full display name."""
    parts = [p.strip() for p in display_name.split(",")]
    if len(parts) >= 2:
        return f"{parts[0]}, {parts[1]}"
    return parts[0] if parts else display_name
