import requests

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"


def get_route(waypoints: list) -> dict:
    """
    Get a driving route between waypoints using the OSRM API.

    Args:
        waypoints: list of {'lat': float, 'lon': float} dicts

    Returns:
        {
            'distance_meters': float,
            'duration_seconds': float,
            'geometry': geojson geometry,
            'legs': list of leg info dicts,
        }
    """
    coords = ";".join(f"{wp['lon']},{wp['lat']}" for wp in waypoints)
    url = f"{OSRM_BASE_URL}/{coords}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
        "annotations": "false",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if data.get("code") != "Ok":
        raise ValueError(f"OSRM routing failed: {data.get('message', 'Unknown error')}")

    route = data["routes"][0]
    legs = route.get("legs", [])
    leg_info = [
        {
            "distance_meters": leg["distance"],
            "duration_seconds": leg["duration"],
        }
        for leg in legs
    ]

    return {
        "distance_meters": route["distance"],
        "duration_seconds": route["duration"],
        "geometry": route["geometry"],
        "legs": leg_info,
    }
