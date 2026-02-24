import json
from datetime import date

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .utils.geocoder import geocode
from .utils.router import get_route
from .utils.hos_calculator import build_trip_schedule, compute_daily_totals
from .utils.log_generator import generate_all_logs


@method_decorator(csrf_exempt, name="dispatch")
class TripPlanView(View):
    """
    POST /api/trip/plan/

    Body (JSON):
    {
        "current_location": "Chicago, IL",
        "pickup_location": "Milwaukee, WI",
        "dropoff_location": "Minneapolis, MN",
        "current_cycle_used": 20.5
    }
    """

    def post(self, request):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        current_location = body.get("current_location", "").strip()
        pickup_location = body.get("pickup_location", "").strip()
        dropoff_location = body.get("dropoff_location", "").strip()
        cycle_used = float(body.get("current_cycle_used", 0))

        if not all([current_location, pickup_location, dropoff_location]):
            return JsonResponse(
                {"error": "current_location, pickup_location, and dropoff_location are required"},
                status=400,
            )

        # 1. Geocode all locations
        try:
            current_geo = geocode(current_location)
            pickup_geo = geocode(pickup_location)
            dropoff_geo = geocode(dropoff_location)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            return JsonResponse({"error": f"Geocoding failed: {e}"}, status=502)

        waypoints = [current_geo, pickup_geo, dropoff_geo]

        # 2. Get route
        try:
            route = get_route(waypoints)
        except Exception as e:
            return JsonResponse({"error": f"Routing failed: {e}"}, status=502)

        # Annotate legs with location names
        locations = [current_geo, pickup_geo, dropoff_geo]
        for i, leg in enumerate(route["legs"]):
            leg["from_location"] = locations[i]["city"]
            leg["to_location"] = locations[i + 1]["city"]

        total_distance_miles = route["distance_meters"] / 1609.34
        total_duration_hours = route["duration_seconds"] / 3600

        # 3. Build HOS schedule
        days = build_trip_schedule(
            current_location=current_geo["city"],
            pickup_location=pickup_geo["city"],
            dropoff_location=dropoff_geo["city"],
            current_cycle_used_hrs=cycle_used,
            route_legs=route["legs"],
            start_hour=6.0,
        )

        # Compute daily totals for the schedule response
        schedule_summary = []
        for day in days:
            totals = compute_daily_totals(day["events"])
            schedule_summary.append({
                "day": day["day"],
                "date_offset": day["date_offset"],
                "events": day["events"],
                "totals": {k: round(v, 2) for k, v in totals.items()},
            })

        # 4. Generate ELD log images
        trip_info = {
            "driver_name": "Driver",
            "carrier": "Trip Tracker Inc.",
            "main_office": current_geo["city"],
            "home_terminal": current_geo["city"],
            "truck_number": "T-001",
            "trailer_number": "TR-001",
            "from_location": current_geo["city"],
            "to_location": dropoff_geo["city"],
            "total_miles": round(total_distance_miles),
            "start_date": date.today(),
        }

        try:
            log_images = generate_all_logs(days, trip_info)
        except Exception as e:
            return JsonResponse({"error": f"Log generation failed: {e}"}, status=500)

        # 5. Build response
        return JsonResponse({
            "route": {
                "waypoints": [
                    {
                        "label": label,
                        "lat": geo["lat"],
                        "lon": geo["lon"],
                        "display_name": geo["city"],
                    }
                    for label, geo in zip(
                        ["Current Location", "Pickup", "Dropoff"],
                        [current_geo, pickup_geo, dropoff_geo],
                    )
                ],
                "geometry": route["geometry"],
                "legs": route["legs"],
                "total_distance_miles": round(total_distance_miles, 1),
                "total_duration_hours": round(total_duration_hours, 2),
            },
            "schedule": schedule_summary,
            "logs": log_images,
        })
