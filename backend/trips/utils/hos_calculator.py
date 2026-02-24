"""
FMCSA Hours of Service (HOS) Calculator.

Rules applied:
- 11-hour driving limit per shift
- 14-hour on-duty window per shift
- 30-minute break required after 8 hours cumulative driving
- 10-hour mandatory rest between shifts (spent in sleeper berth, Line 2)
- 70-hour / 8-day cycle limit
- End of day: post-trip TIV (on-duty, 30 min) followed by sleeper berth (Line 2)
"""

DRIVE_LIMIT_HRS = 11.0       # Max driving hours per shift
DUTY_WINDOW_HRS = 14.0       # Max on-duty window hours per shift
BREAK_AFTER_HRS = 8.0        # Hours of driving before mandatory 30-min break
BREAK_DURATION_HRS = 0.5     # 30-minute mandatory break
REST_DURATION_HRS = 10.0     # Minimum off-duty between shifts
PRE_TRIP_HRS = 0.5           # Pre-trip inspection duration
POST_TRIP_HRS = 0.5          # Post-trip inspection duration
LOADING_HRS = 0.5            # Loading/unloading duration at stops
FUELING_HRS = 0.25           # Fueling stop duration (every ~500 miles)
FUELING_MILES = 500          # Miles between fuel stops
AVG_SPEED_MPH = 55           # Average driving speed


def build_trip_schedule(
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    current_cycle_used_hrs: float,
    route_legs: list,
    start_hour: float = 6.0,
) -> list:
    """
    Build a day-by-day schedule for the trip.

    Args:
        current_location: name of current location
        pickup_location: name of pickup location
        dropoff_location: name of dropoff location
        current_cycle_used_hrs: hours already used in 70-hr cycle
        route_legs: list of {'distance_meters', 'duration_seconds', 'from_location', 'to_location'}
        start_hour: hour of day the driver starts (0-24)

    Returns:
        list of day schedules, each containing:
        {
            'day': int,
            'date_offset': int,
            'events': list of event dicts,
        }
    """
    # Convert leg durations to hours
    legs_hours = []
    for leg in route_legs:
        legs_hours.append({
            "drive_hours": leg["duration_seconds"] / 3600,
            "distance_miles": leg["distance_meters"] / 1609.34,
            "from_location": leg.get("from_location", ""),
            "to_location": leg.get("to_location", ""),
        })

    # Build flat list of driving segments with stops
    segments = []

    # Segment 1: current → pickup (driving + loading)
    if legs_hours:
        leg = legs_hours[0]
        segments.append({
            "type": "drive",
            "hours": leg["drive_hours"],
            "distance_miles": leg["distance_miles"],
            "from_loc": leg["from_location"],
            "to_loc": leg["to_location"],
        })
        segments.append({
            "type": "on_duty_stop",
            "hours": LOADING_HRS,
            "location": leg["to_location"],
            "remark": "Pickup/Loading",
        })

    # Segment 2: pickup → dropoff (driving + unloading)
    if len(legs_hours) > 1:
        leg = legs_hours[1]
        segments.append({
            "type": "drive",
            "hours": leg["drive_hours"],
            "distance_miles": leg["distance_miles"],
            "from_loc": leg["from_location"],
            "to_loc": leg["to_location"],
        })
    segments.append({
        "type": "on_duty_stop",
        "hours": LOADING_HRS,
        "location": dropoff_location,
        "remark": "Dropoff/Unloading",
    })

    # Now schedule into days
    days = []
    day_num = 0
    current_time = start_hour  # Time within current day (hours)
    cycle_used = current_cycle_used_hrs

    # Shift tracking
    shift_drive_hrs = 0.0      # Driving hours in current shift
    shift_duty_hrs = 0.0       # On-duty hours in current shift (14-hr window)
    drive_since_break = 0.0    # Driving since last 30-min break
    miles_since_fuel = 0.0     # Miles since last fuel stop
    shift_start_time = None    # Time when current shift started (for 14-hr window)

    def start_new_day(day_no, start_t=0.0):
        return {
            "day": day_no + 1,
            "date_offset": day_no,
            "events": [],
        }

    def add_event(day, time, status, location, remark=""):
        day["events"].append({
            "time": round(time, 4),
            "status": status,
            "location": location,
            "remark": remark,
        })

    # Start first day
    current_day = start_new_day(day_num)
    current_location_name = current_location

    # Begin at start_hour with off-duty until then
    if current_time > 0:
        add_event(current_day, 0, "off_duty", current_location_name, "")

    # Pre-trip inspection (on-duty, not driving)
    add_event(current_day, current_time, "on_duty", current_location_name, "Pre-trip inspection")
    shift_start_time = current_time
    current_time += PRE_TRIP_HRS
    shift_duty_hrs += PRE_TRIP_HRS

    # Switch to driving
    def needs_rest():
        """Check if driver needs a 10-hour rest break."""
        return (
            shift_drive_hrs >= DRIVE_LIMIT_HRS
            or shift_duty_hrs >= DUTY_WINDOW_HRS
        )

    def time_to_next_rest():
        """Hours of driving remaining before mandatory rest."""
        drive_remaining = DRIVE_LIMIT_HRS - shift_drive_hrs
        window_remaining = DUTY_WINDOW_HRS - shift_duty_hrs
        return min(drive_remaining, window_remaining)

    def do_rest(day, t, loc):
        """Record 10-hour rest period, possibly spanning midnight."""
        nonlocal current_time, day_num, current_day, shift_drive_hrs
        nonlocal shift_duty_hrs, drive_since_break, shift_start_time

        add_event(day, t, "sleeper_berth", loc, "10-hour rest")
        rest_remaining = REST_DURATION_HRS
        ct = t

        while rest_remaining > 0:
            time_left_in_day = 24.0 - ct
            if rest_remaining <= time_left_in_day:
                ct += rest_remaining
                rest_remaining = 0
            else:
                # Finish the day
                if ct < 24.0:
                    days.append(day)
                day_num += 1
                day = start_new_day(day_num)
                add_event(day, 0, "sleeper_berth", loc, "")
                rest_remaining -= time_left_in_day
                ct = 0.0

        current_day = day
        current_time = ct
        shift_drive_hrs = 0.0
        shift_duty_hrs = 0.0
        drive_since_break = 0.0
        shift_start_time = None
        return day, ct

    seg_idx = 0
    total_segments = len(segments)

    while seg_idx < total_segments:
        seg = segments[seg_idx]

        if seg["type"] == "drive":
            # Need to start driving
            add_event(current_day, current_time, "driving", current_location_name, "")
            if shift_start_time is None:
                shift_start_time = current_time

            drive_hours_remaining = seg["hours"]
            seg_miles = seg.get("distance_miles", 0)
            seg_from = seg.get("from_loc", current_location_name)
            seg_to = seg.get("to_loc", "")

            while drive_hours_remaining > 0:
                # Check fuel
                if miles_since_fuel + seg_miles > FUELING_MILES and seg_miles > 0:
                    # Need a fuel stop roughly partway through
                    miles_to_fuel = FUELING_MILES - miles_since_fuel
                    fraction_to_fuel = min(miles_to_fuel / seg_miles, 1.0) if seg_miles > 0 else 1.0
                    hrs_to_fuel = drive_hours_remaining * fraction_to_fuel
                else:
                    hrs_to_fuel = drive_hours_remaining

                # How many hours can we drive before forced break?
                if drive_since_break >= BREAK_AFTER_HRS:
                    # Need break now
                    add_event(current_day, current_time, "off_duty",
                              current_location_name, "30-min break")
                    current_time += BREAK_DURATION_HRS
                    shift_duty_hrs += BREAK_DURATION_HRS
                    drive_since_break = 0.0
                    add_event(current_day, current_time, "driving", current_location_name, "")
                    continue

                hrs_before_break = BREAK_AFTER_HRS - drive_since_break
                hrs_before_rest = time_to_next_rest()

                # Time left before midnight
                hrs_to_midnight = 24.0 - current_time

                drive_chunk = min(
                    drive_hours_remaining,
                    hrs_to_fuel,
                    hrs_before_break,
                    hrs_before_rest,
                    hrs_to_midnight,
                )

                if drive_chunk <= 0:
                    drive_chunk = 0.001  # safety

                # Drive the chunk
                current_time += drive_chunk
                shift_drive_hrs += drive_chunk
                shift_duty_hrs += drive_chunk
                drive_since_break += drive_chunk
                drive_hours_remaining -= drive_chunk
                miles_driven = seg_miles * (drive_chunk / seg["hours"]) if seg["hours"] > 0 else 0
                miles_since_fuel += miles_driven
                seg_miles -= miles_driven

                current_location_name = seg_to if drive_hours_remaining <= 0.001 else seg_from

                # Check if we hit midnight
                if current_time >= 24.0 - 0.001:
                    days.append(current_day)
                    day_num += 1
                    current_day = start_new_day(day_num)
                    current_time = 0.0
                    add_event(current_day, 0, "driving", current_location_name, "")
                    continue

                # Check mandatory 30-min break
                if drive_since_break >= BREAK_AFTER_HRS - 0.001:
                    add_event(current_day, current_time, "off_duty",
                              current_location_name, "30-min break")
                    current_time += BREAK_DURATION_HRS
                    shift_duty_hrs += BREAK_DURATION_HRS
                    drive_since_break = 0.0
                    add_event(current_day, current_time, "driving", current_location_name, "")
                    continue

                # Check fuel stop
                if miles_since_fuel >= FUELING_MILES - 0.1:
                    add_event(current_day, current_time, "on_duty",
                              current_location_name, "Fuel stop")
                    current_time += FUELING_HRS
                    shift_duty_hrs += FUELING_HRS
                    miles_since_fuel = 0.0
                    add_event(current_day, current_time, "driving", current_location_name, "")
                    continue

                # Check mandatory rest (only if there is more driving to do)
                if needs_rest():
                    if drive_hours_remaining <= 0.001:
                        # Driving complete – let the next segment handle the rest
                        break
                    current_day, current_time = do_rest(
                        current_day, current_time, current_location_name
                    )
                    shift_start_time = None
                    # Resume driving after rest
                    add_event(current_day, current_time, "on_duty",
                              current_location_name, "Pre-trip inspection")
                    shift_start_time = current_time
                    current_time += PRE_TRIP_HRS
                    shift_duty_hrs += PRE_TRIP_HRS
                    add_event(current_day, current_time, "driving", current_location_name, "")
                    continue

            current_location_name = seg.get("to_loc", current_location_name)
            seg_idx += 1

        elif seg["type"] == "on_duty_stop":
            loc = seg.get("location", current_location_name)
            remark = seg.get("remark", "")
            stop_hrs = seg["hours"]

            # Do the stop first, then check if rest is needed after
            add_event(current_day, current_time, "on_duty", loc, remark)
            current_time += stop_hrs
            shift_duty_hrs += stop_hrs

            if shift_start_time is None:
                shift_start_time = current_time - stop_hrs

            # Handle midnight crossing
            if current_time >= 24.0:
                days.append(current_day)
                day_num += 1
                current_day = start_new_day(day_num)
                current_time = current_time - 24.0
                add_event(current_day, 0, "on_duty", loc, remark)

            current_location_name = loc

            # After completing the stop, take rest if needed
            if needs_rest():
                current_day, current_time = do_rest(
                    current_day, current_time, current_location_name
                )
                shift_start_time = None

            seg_idx += 1

    # Post-trip inspection
    if needs_rest():
        current_day, current_time = do_rest(
            current_day, current_time, current_location_name
        )
        shift_start_time = None

    add_event(current_day, current_time, "on_duty",
              current_location_name, "Post-trip inspection")
    current_time += POST_TRIP_HRS
    shift_duty_hrs += POST_TRIP_HRS

    # Rest at end of trip — driver is in sleeper berth (Line 2)
    add_event(current_day, current_time, "sleeper_berth",
              current_location_name, "End of shift")

    # Fill to end of day
    if current_time < 24.0:
        pass  # The last event carries to end of day

    days.append(current_day)
    return days


def compute_daily_totals(events: list) -> dict:
    """
    Given a list of events for one day, compute hours per status.
    Events must be sorted by time. Each event's status runs from its
    time until the next event's time (or midnight).

    Returns: {'off_duty': h, 'sleeper_berth': h, 'driving': h, 'on_duty': h}
    """
    totals = {"off_duty": 0.0, "sleeper_berth": 0.0, "driving": 0.0, "on_duty": 0.0}
    if not events:
        return totals

    sorted_events = sorted(events, key=lambda e: e["time"])

    for i, event in enumerate(sorted_events):
        start_t = event["time"]
        end_t = sorted_events[i + 1]["time"] if i + 1 < len(sorted_events) else 24.0
        duration = max(0.0, end_t - start_t)
        status = event["status"]
        if status in totals:
            totals[status] += duration

    return totals
