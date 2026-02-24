"""
ELD (Electronic Logging Device) Daily Log Generator.

Draws driver daily log entries on the blank template image using PIL.

Template image: files/template/blank-driver-log.png (513x518 pixels)

Grid coordinates (confirmed by pixel analysis):
  - Grid left edge (midnight start): x=56
  - Grid right edge (midnight end): x=491
  - Grid width for 24 hours: 435 pixels
  - Pixels per hour: 435/24 = 18.125

  Row center Y positions (between horizontal border lines):
  - Off Duty (y=184–201):        center y=192
  - Sleeper Berth (y=201–218):   center y=209
  - Driving (y=218–235):         center y=226
  - On Duty not driving (y=235–252): center y=243
"""

import io
import base64
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings

# ── Grid constants ────────────────────────────────────────────────────────────
GRID_LEFT = 56          # x pixel for midnight (hour 0)
GRID_RIGHT = 491        # x pixel for midnight (hour 24)
GRID_WIDTH = GRID_RIGHT - GRID_LEFT   # 435 pixels = 24 hours

# Row centre Y positions (drawing line centre for each duty status)
ROW_Y = {
    "off_duty": 192,
    "sleeper_berth": 209,
    "driving": 226,
    "on_duty": 243,
}

# Row bottom Y positions (for drawing remarks flags from)
ROW_BOTTOM = {
    "off_duty": 201,
    "sleeper_berth": 218,
    "driving": 235,
    "on_duty": 252,
}

LINE_COLOR = (0, 0, 0)
DOT_COLOR = (180, 0, 0)
LINE_WIDTH = 2
DOT_RADIUS = 3

# ── Hours column x position (right side of grid) ─────────────────────────────
HOURS_X = 497


def _time_to_x(hour_fraction: float) -> int:
    """Convert time in fractional hours (0–24) to x pixel position."""
    return int(round(GRID_LEFT + (hour_fraction / 24.0) * GRID_WIDTH))


def _load_font(size=7):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _load_bold_font(size=7):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def generate_log_image(
    day_info: dict,
    trip_info: dict,
    day_number: int,
    total_days: int,
) -> str:
    """
    Generate a single ELD daily log image and return it as a base64 PNG string.

    Args:
        day_info: dict with keys:
            - 'date_offset': int (0 = first day of trip)
            - 'events': list of event dicts:
                {'time': float, 'status': str, 'location': str, 'remark': str}
        trip_info: trip metadata dict
        day_number: 1-based day number
        total_days: total number of days in trip

    Returns:
        Base64-encoded PNG string.
    """
    template_path = str(settings.LOG_TEMPLATE_PATH)
    img = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_sm = _load_font(7)
    font_md = _load_font(8)
    font_lg = _load_bold_font(9)

    events = day_info.get("events", [])

    # ── Draw header ───────────────────────────────────────────────────────────
    _draw_header(draw, day_info, trip_info, font_sm, font_md)

    if not events:
        return _image_to_base64(img)

    # ── Normalise events – ensure coverage starts at 0:00 ────────────────────
    sorted_events = sorted(events, key=lambda e: e["time"])
    if sorted_events[0]["time"] > 0:
        sorted_events = [{
            "time": 0.0,
            "status": "off_duty",
            "location": sorted_events[0].get("location", ""),
            "remark": "",
        }] + sorted_events

    # ── Draw duty-status lines on the grid ────────────────────────────────────
    _draw_grid_lines(draw, sorted_events)

    # ── Draw hours totals (right column) ─────────────────────────────────────
    from .hos_calculator import compute_daily_totals
    totals = compute_daily_totals(events)
    _draw_hours_column(draw, totals, font_sm)

    # ── Draw remarks flags ───────────────────────────────────────────────────
    _draw_remarks_flags(draw, sorted_events, font_sm, img)

    # ── Draw bottom totals ───────────────────────────────────────────────────
    _draw_bottom_totals(draw, totals, font_md, font_lg)

    return _image_to_base64(img)


# ─────────────────────────────────────────────────────────────────────────────
#  Sub-drawing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _draw_header(draw, day_info, trip_info, font_sm, font_md):
    """Fill in the header section of the log sheet."""
    from datetime import date, timedelta

    try:
        start_date = trip_info.get("start_date")
        trip_date = (start_date + timedelta(days=day_info.get("date_offset", 0))
                     if start_date else date.today())
    except Exception:
        trip_date = date.today()

    blue = (0, 0, 180)

    # ── Date (month / day / year) ─────────────────────────────────────────
    # The "/" separators are printed in the template at approximately x=155, 205
    # Month value goes left of first slash (x≈118), Day between slashes (x≈172), Year after second (x≈220)
    draw.text((118, 19), str(trip_date.month), fill=blue, font=font_md)
    draw.text((172, 19), str(trip_date.day), fill=blue, font=font_md)
    draw.text((220, 19), str(trip_date.year), fill=blue, font=font_md)

    # ── From / To ─────────────────────────────────────────────────────────
    # "From:" label is printed; text goes just to its right on the same line (~y=46)
    from_loc = _truncate(trip_info.get("from_location", ""), 25)
    to_loc = _truncate(trip_info.get("to_location", ""), 25)
    draw.text((38, 47), from_loc, fill=blue, font=font_sm)
    draw.text((263, 47), to_loc, fill=blue, font=font_sm)

    # ── Mileage boxes ────────────────────────────────────────────────────
    # Left box = Total Miles Driving Today (x=54–134, y=68–80)
    # Right box = Total Mileage Today (x=141–215, y=68–80)
    miles = int(trip_info.get("total_miles", 0))
    draw.text((85, 72), str(miles), fill=blue, font=font_md)
    draw.text((155, 72), str(miles), fill=blue, font=font_md)

    # ── Truck / Trailer numbers ──────────────────────────────────────────
    truck = trip_info.get("truck_number", "")
    trailer = trip_info.get("trailer_number", "")
    draw.text((63, 105), f"{truck} / {trailer}", fill=blue, font=font_sm)

    # ── Carrier / Office / Terminal (right side) ─────────────────────────
    # Labels are: "Name of Carrier or Carriers" (y≈68–76), "Main Office" (y≈80–88), "Home Terminal" (y≈93–101)
    # Values go on the blank line ABOVE each label
    carrier = _truncate(trip_info.get("carrier", ""), 35)
    office = _truncate(trip_info.get("main_office", ""), 35)
    terminal = _truncate(trip_info.get("home_terminal", ""), 35)
    draw.text((262, 61), carrier, fill=blue, font=font_sm)
    draw.text((262, 74), office, fill=blue, font=font_sm)
    draw.text((262, 87), terminal, fill=blue, font=font_sm)


def _draw_grid_lines(draw, sorted_events):
    """Draw horizontal status lines and vertical connectors on the grid."""
    for i, event in enumerate(sorted_events):
        t_start = event["time"]
        t_end = sorted_events[i + 1]["time"] if i + 1 < len(sorted_events) else 24.0

        status = event["status"]
        if status not in ROW_Y:
            status = "off_duty"

        x_start = _time_to_x(t_start)
        x_end = _time_to_x(t_end)
        y = ROW_Y[status]

        # Horizontal line for this period
        if x_end > x_start:
            draw.line([(x_start, y), (x_end, y)], fill=LINE_COLOR, width=LINE_WIDTH)

        # Vertical connector at status change (i > 0)
        if i > 0:
            prev_status = sorted_events[i - 1]["status"]
            if prev_status not in ROW_Y:
                prev_status = "off_duty"
            prev_y = ROW_Y[prev_status]
            if prev_y != y:
                draw.line([(x_start, prev_y), (x_start, y)],
                          fill=LINE_COLOR, width=LINE_WIDTH)

        # Red dot at transition point
        if i > 0 or t_start > 0:
            draw.ellipse(
                [(x_start - DOT_RADIUS, y - DOT_RADIUS),
                 (x_start + DOT_RADIUS, y + DOT_RADIUS)],
                fill=DOT_COLOR,
            )

    # Final dot at end of last segment
    if sorted_events:
        last = sorted_events[-1]
        last_status = last["status"] if last["status"] in ROW_Y else "off_duty"
        last_y = ROW_Y[last_status]
        draw.ellipse(
            [(GRID_RIGHT - DOT_RADIUS, last_y - DOT_RADIUS),
             (GRID_RIGHT + DOT_RADIUS, last_y + DOT_RADIUS)],
            fill=DOT_COLOR,
        )


def _draw_hours_column(draw, totals, font_sm):
    """Write the hours totals in the column to the right of the grid."""
    # Y positions match ROW_Y centres
    y_map = {
        "off_duty": ROW_Y["off_duty"] - 4,
        "sleeper_berth": ROW_Y["sleeper_berth"] - 4,
        "driving": ROW_Y["driving"] - 4,
        "on_duty": ROW_Y["on_duty"] - 4,
    }
    for status, y in y_map.items():
        val = totals.get(status, 0.0)
        draw.text((HOURS_X, y), _fmt_hours(val), fill=(0, 0, 0), font=font_sm)


def _draw_remarks_flags(draw, sorted_events, font_sm, img):
    """
    Draw remarks flags: a short vertical line down from the grid row bottom,
    then a diagonal line, then rotated text with location + remark.
    """
    remarks_base_y = 262   # Y position where flag vertical lines start

    # Only events that have a remark OR a location different from previous
    flag_events = []
    for i, ev in enumerate(sorted_events):
        remark = ev.get("remark", "").strip()
        location = ev.get("location", "").strip()
        prev_loc = sorted_events[i - 1].get("location", "") if i > 0 else ""
        if remark or (i > 0 and location != prev_loc):
            flag_events.append(ev)

    for ev in flag_events:
        t = ev["time"]
        x = _time_to_x(t)
        status = ev.get("status", "off_duty")
        if status not in ROW_BOTTOM:
            status = "off_duty"

        y_bottom = ROW_BOTTOM[status]

        # Short vertical line from grid bottom to remarks area
        draw.line([(x, y_bottom), (x, remarks_base_y)], fill=(0, 0, 0), width=1)

        # Diagonal flag line
        flag_end_x = x + 18
        flag_end_y = remarks_base_y + 25
        draw.line([(x, remarks_base_y), (flag_end_x, flag_end_y)], fill=(0, 0, 0), width=1)

        # Build text
        location = ev.get("location", "").strip()
        remark = ev.get("remark", "").strip()
        text_lines = []
        if location:
            text_lines.append(location)
        if remark:
            text_lines.append(remark)

        if text_lines:
            text = "\n".join(text_lines)
            _paste_rotated_text(img, draw, text, flag_end_x + 1, flag_end_y, font_sm, -45)


def _paste_rotated_text(img, draw, text, x, y, font, angle_degrees):
    """Render text into a temporary image, rotate it, and paste onto img."""
    lines = text.split("\n")
    # Estimate text dimensions
    char_w, char_h = 5, 8
    max_len = max(len(line) for line in lines)
    txt_w = max_len * char_w + 6
    txt_h = len(lines) * (char_h + 2) + 4

    txt_img = Image.new("RGBA", (txt_w, txt_h), (255, 255, 255, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.text((2, 2), text, fill=(0, 0, 180, 255), font=font)

    rotated = txt_img.rotate(angle_degrees, expand=True)
    try:
        img.paste(rotated, (int(x), int(y)), rotated)
    except Exception:
        draw.text((x, y), text.replace("\n", " "), fill=(0, 0, 180), font=font)


def _draw_bottom_totals(draw, totals, font_md, font_lg):
    """Draw driving / on-duty / total hours summary in the remarks area."""
    driving = totals.get("driving", 0.0)
    on_duty = totals.get("on_duty", 0.0)
    total = driving + on_duty

    y = 346
    draw.text((60, y),
              f"Driving: {_fmt_hours(driving)}",
              fill=(0, 0, 0), font=font_md)
    draw.text((160, y),
              f"On Duty (not driving): {_fmt_hours(on_duty)}",
              fill=(0, 0, 0), font=font_md)

    total_str = f"{total:.1f}"
    tx = 360
    draw.text((tx, y), f"Total: {total_str} hrs", fill=(0, 0, 0), font=font_lg)
    # Circle around total value
    circ_x0 = tx + 38
    circ_y0 = y - 1
    circ_x1 = circ_x0 + len(total_str) * 7 + 2
    circ_y1 = circ_y0 + 11
    draw.ellipse([(circ_x0, circ_y0), (circ_x1, circ_y1)], outline=(0, 0, 0), width=1)


# ─────────────────────────────────────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_hours(h: float) -> str:
    hrs = int(h)
    mins = int(round((h - hrs) * 60))
    if mins >= 60:
        hrs += 1
        mins = 0
    return f"{hrs}:{mins:02d}"


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def _image_to_base64(img: Image.Image) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def generate_all_logs(days: list, trip_info: dict) -> list:
    """
    Generate ELD log images for all days of a trip.

    Args:
        days: list of day dicts from hos_calculator.build_trip_schedule()
        trip_info: trip metadata dict

    Returns:
        list of dicts: [{'day': int, 'date_offset': int, 'image_base64': str}, ...]
    """
    total_days = len(days)
    return [
        {
            "day": i + 1,
            "date_offset": day.get("date_offset", i),
            "image_base64": generate_log_image(day, trip_info, i + 1, total_days),
        }
        for i, day in enumerate(days)
    ]

