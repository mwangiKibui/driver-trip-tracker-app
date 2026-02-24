"""
ELD (Electronic Logging Device) Daily Log Generator.

Draws driver daily log entries on the blank template image using PIL.

Template image: files/template/blank-driver-log.png (513x518 pixels)

Grid coordinate reference (confirmed by pixel analysis):
  - Grid left edge  (midnight start): GRID_LEFT  = 56
  - Grid right edge (midnight end):   GRID_RIGHT = 491
  - Grid width for 24 hours:          GRID_WIDTH = 435
  - Pixels per hour:                  435 / 24 ≈ 18.125

  Duty-status row centre Y positions:
  - Off Duty (y=184–201):              ROW_Y["off_duty"]      = 192
  - Sleeper Berth (y=201–218):         ROW_Y["sleeper_berth"] = 209
  - Driving (y=218–235):               ROW_Y["driving"]       = 226
  - On Duty not driving (y=235–252):   ROW_Y["on_duty"]       = 243
"""

import io
import base64
import textwrap
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings

# ── Grid constants ─────────────────────────────────────────────────────────────
GRID_LEFT = 56          # x pixel for midnight (hour 0)
GRID_RIGHT = 465        # x pixel where drawn status lines end (was 491 – shortened
                        #   to create space for the hours column at HOURS_COL_X)
GRID_WIDTH = GRID_RIGHT - GRID_LEFT   # pixels = 24 hours

# Duty-status row centre Y positions
ROW_Y = {
    "off_duty":      192,
    "sleeper_berth": 209,
    "driving":       226,
    "on_duty":       243,
}

# Bottom edge of each duty-status row (start of remarks drop-lines)
ROW_BOTTOM = {
    "off_duty":      201,
    "sleeper_berth": 218,
    "driving":       235,
    "on_duty":       252,
}

# ── Colours ────────────────────────────────────────────────────────────────────
LINE_COLOR    = (0,   0,   0)    # grid lines / connectors
DOT_COLOR     = (180, 0,   0)    # status-change dots (dark red)
TEXT_BLACK    = (0,   0,   0)    # body text
TEXT_BLUE     = (0,   0, 180)    # header fill text
CIRCLE_RED    = (200, 0,   0)    # total-hours circle outline (red)

# ── Line weights ───────────────────────────────────────────────────────────────
LINE_WIDTH    = 2
DOT_RADIUS    = 3
CIRCLE_WIDTH  = 2   # thickness of the red total-hours circle

# ── Header field positions ─────────────────────────────────────────────────────
# Date: input values sit ABOVE the underline at y=19, centred under each sub-label.
#   "(month)" sub-label centre x≈187, "(day)" centre x≈227, "(year)" centre x≈271.
HDR_DATE_Y       = 7     # y for date values (pushed further above underline at y=19)
HDR_DATE_MONTH_X = 182   # x for month value (centred under "(month)" label)
HDR_DATE_DAY_X   = 223   # x for day value   (centred under "(day)"   label)
HDR_DATE_YEAR_X  = 255   # x for year value  (centred under "(year)"  label)

# From / To: values go on the same row as the printed "From:" / "To:" labels.
#   "From:" label ends at x≈86 (y=40-43); "To:" label ends at x≈270 (y=40-43).
HDR_FROM_TO_Y    = 37    # y for From / To row (pushed up above the label text)
HDR_FROM_X       = 90    # x for "from" value (just right of "From:" label)
HDR_TO_X         = 278   # x for "to"   value (just right of "To:"   label)

HDR_MILES_Y      = 72    # y for mileage row
HDR_MILES_DRV_X  = 85    # x for "Total Miles Driving Today"
HDR_MILES_TOT_X  = 155   # x for "Total Mileage Today"

HDR_TRUCK_X      = 63    # x for truck / trailer numbers
HDR_TRUCK_Y      = 105   # y for truck / trailer numbers

# Right block (carrier / office / terminal): values sit ABOVE each printed underline.
#   Carrier underline y=79, Office underline y=99, Terminal underline y=120.
#   Right block starts at x=229; left-pad 5px → text starts at x=234.
HDR_CARRIER_X    = 234   # x for carrier / office / terminal (right block)
HDR_CARRIER_Y    = 68    # y for carrier name  (above underline at y=79)
HDR_OFFICE_Y     = 88    # y for main office   (above underline at y=99)
HDR_TERMINAL_Y   = 109   # y for home terminal (above underline at y=120)

# ── Hours column ───────────────────────────────────────────────────────────────
# The grid lines are drawn from GRID_LEFT to GRID_RIGHT. By stopping the lines
# at x=465 (rather than the pre-printed right border at x=491) we create a
# 26 px gap that lets the hours text sit visibly away from the right edge.
# HOURS_COL_X is placed just after GRID_RIGHT so the values appear in that gap.
HOURS_COL_X      = 467   # left edge of hours text (was 493 – moved left)
HOURS_FONT_SIZE  = 6     # small enough for "H:MM" to fit in available space

# ── Remarks section ────────────────────────────────────────────────────────────
REMARKS_BASE_Y           = 255   # y where vertical drop-lines land
REMARKS_TEXT_SIZE        = 5     # font size for rotated remarks text (small to prevent overlap)
REMARKS_WRAP_CHARS       = 10    # max chars per line before word-wrapping
REMARKS_MIN_TEXT_SPACING = 20    # min x-gap (px) between rendered text labels;
                                 # labels closer than this are suppressed to avoid collision
REMARKS_LINE_SPACING     = 3     # extra px between lines when estimating text block height
REMARKS_TEXT_PADDING     = 2     # extra px padding added to text block height estimate

# ── Bottom totals ──────────────────────────────────────────────────────────────
# Layout at TOTALS_Y (y≈346, in the Remarks free-write area):
#   "Driving: H:MM"            starts at TOTALS_DRV_X  (≈57px wide at 8pt)
#   "On Duty (not driving):…"  starts at TOTALS_DUTY_X (≈108px wide at 8pt)
#   Circled total value         starts at TOTALS_SUM_X
# Widths: driving≈57px, gap≈10, on-duty≈108px → on-duty ends ≈x=278
# Place total at x=270 so the whole group fits within 513px.
TOTALS_Y         = 346   # y of the summary row
TOTALS_DRV_X     = 60    # x for "Driving: ..." label
TOTALS_DUTY_X    = 160   # x for "On Duty (not driving): ..." label
TOTALS_SUM_X     = 295   # x for total value + circle (was 355 – moved left)

# Red circle around the on-duty total: centred on the number
TOTAL_CIRCLE_PAD_X = 8   # horizontal padding inside circle
TOTAL_CIRCLE_PAD_Y = 4   # vertical padding inside circle


# ── Font helpers ───────────────────────────────────────────────────────────────

def _load_font(size: int = 7) -> ImageFont.FreeTypeFont:
    """Load DejaVu Sans (or fallback) at the requested point size."""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _load_bold_font(size: int = 7) -> ImageFont.FreeTypeFont:
    """Load DejaVu Sans Bold (or fallback) at the requested point size."""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ── Coordinate helpers ─────────────────────────────────────────────────────────

def _time_to_x(hour_fraction: float) -> int:
    """Convert fractional hours (0–24) to x pixel position on the grid."""
    return int(round(GRID_LEFT + (hour_fraction / 24.0) * GRID_WIDTH))


def _fmt_hours(h: float) -> str:
    """Format a decimal hour value as H:MM (e.g. 11.5 → '11:30')."""
    hrs = int(h)
    mins = int(round((h - hrs) * 60))
    if mins >= 60:
        hrs += 1
        mins = 0
    return f"{hrs}:{mins:02d}"


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending '…' if needed."""
    return text if len(text) <= max_chars else text[:max_chars - 1] + "\u2026"


# US state name → 2-letter abbreviation (used to shorten location strings)
_STATE_ABBREVS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}


def _abbrev_location(text: str) -> str:
    """
    Shorten a location string to 'City, ST' format.

    Input formats handled:
      - 'City, County, State'  → 'City, ST'
      - 'City, State'          → 'City, ST'
      - 'City'                 → 'City' (truncated to 15 chars if needed)

    The county segment (middle part) is dropped entirely.
    State names are converted to 2-letter abbreviations.
    """
    if not text:
        return text
    parts = [p.strip() for p in text.split(",")]
    city = parts[0].strip()
    state_abbrev = ""
    for part in reversed(parts[1:]):
        part_clean = part.strip()
        if part_clean in _STATE_ABBREVS:
            state_abbrev = _STATE_ABBREVS[part_clean]
            break
        if part_clean in _STATE_ABBREVS.values():
            # Already a 2-letter abbreviation
            state_abbrev = part_clean
            break
    if state_abbrev:
        return f"{city}, {state_abbrev}"
    # No recognizable state: return city truncated to 15 chars
    return city[:15]


def _wrap_remark(text: str) -> str:
    """
    Wrap a remark string at REMARKS_WRAP_CHARS characters per line.

    Short words are kept together; long single words that exceed the limit
    are left on their own line rather than broken mid-word.
    Returns the wrapped text with newline separators.
    """
    if not text:
        return text
    lines = textwrap.wrap(text, width=REMARKS_WRAP_CHARS, break_long_words=False,
                          break_on_hyphens=True)
    return "\n".join(lines) if lines else text


def _image_to_base64(img: Image.Image) -> str:
    """Encode a PIL image as a base64 PNG string."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ── Rotated-text compositor ────────────────────────────────────────────────────

def _paste_rotated_text(
    img: Image.Image,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    angle_degrees: float,
) -> None:
    """
    Render *text* into a temporary RGBA canvas, rotate it, then
    alpha-composite the result onto *img* (which may be RGB).

    Using ``Image.alpha_composite`` (rather than ``paste(..., mask=...)``
    avoids the anti-aliasing fade that the mask-paste approach produces when
    the base image is RGB: PIL cannot composite RGBA→RGB via paste masks
    without precision loss on the semi-transparent edge pixels.
    """
    lines = text.split("\n")
    # Measure text size with a temporary draw context
    tmp = Image.new("RGBA", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp)
    line_bboxes = [tmp_draw.textbbox((0, 0), ln, font=font) for ln in lines]
    txt_w = max(bb[2] - bb[0] for bb in line_bboxes) + 8
    line_h = max((bb[3] - bb[1]) for bb in line_bboxes) + 2
    txt_h = len(lines) * line_h + 6

    # Draw on a transparent RGBA canvas
    txt_img = Image.new("RGBA", (max(txt_w, 1), max(txt_h, 1)), (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    for i, line in enumerate(lines):
        txt_draw.text((4, 3 + i * line_h), line, fill=(0, 0, 0, 255), font=font)

    # Rotate (expand=True grows the canvas; new pixels are transparent)
    rotated = txt_img.rotate(angle_degrees, expand=True, resample=Image.BICUBIC)

    # Destination rectangle (clipped to image bounds)
    rx, ry = int(x), int(y)
    rw, rh = rotated.size
    x0 = max(0, rx)
    y0 = max(0, ry)
    x1 = min(img.width,  rx + rw)
    y1 = min(img.height, ry + rh)
    if x1 <= x0 or y1 <= y0:
        return

    # Crop rotated image to the visible region
    crop = rotated.crop((x0 - rx, y0 - ry, x1 - rx, y1 - ry))

    # Alpha-composite: convert base patch to RGBA, composite, paste back as RGB
    base_patch = img.crop((x0, y0, x1, y1)).convert("RGBA")
    composited = Image.alpha_composite(base_patch, crop)
    img.paste(composited.convert("RGB"), (x0, y0))


# ── Section drawing helpers ────────────────────────────────────────────────────

def _draw_header(
    draw: ImageDraw.ImageDraw,
    day_info: dict,
    trip_info: dict,
    font_sm: ImageFont.FreeTypeFont,
    font_md: ImageFont.FreeTypeFont,
) -> None:
    """Fill in the top header section of the log sheet."""
    from datetime import date, timedelta

    try:
        start = trip_info.get("start_date")
        trip_date = (start + timedelta(days=day_info.get("date_offset", 0))
                     if start else date.today())
    except Exception:
        trip_date = date.today()

    # Date
    draw.text((HDR_DATE_MONTH_X, HDR_DATE_Y), str(trip_date.month),
              fill=TEXT_BLUE, font=font_md)
    draw.text((HDR_DATE_DAY_X,   HDR_DATE_Y), str(trip_date.day),
              fill=TEXT_BLUE, font=font_md)
    draw.text((HDR_DATE_YEAR_X,  HDR_DATE_Y), str(trip_date.year),
              fill=TEXT_BLUE, font=font_md)

    # From / To locations
    draw.text((HDR_FROM_X, HDR_FROM_TO_Y),
              _truncate(trip_info.get("from_location", ""), 25),
              fill=TEXT_BLUE, font=font_sm)
    draw.text((HDR_TO_X, HDR_FROM_TO_Y),
              _truncate(trip_info.get("to_location", ""), 25),
              fill=TEXT_BLUE, font=font_sm)

    # Mileage
    miles = int(trip_info.get("total_miles", 0))
    draw.text((HDR_MILES_DRV_X, HDR_MILES_Y), str(miles),
              fill=TEXT_BLUE, font=font_md)
    draw.text((HDR_MILES_TOT_X, HDR_MILES_Y), str(miles),
              fill=TEXT_BLUE, font=font_md)

    # Truck / trailer
    truck   = trip_info.get("truck_number", "")
    trailer = trip_info.get("trailer_number", "")
    draw.text((HDR_TRUCK_X, HDR_TRUCK_Y),
              f"{truck} / {trailer}", fill=TEXT_BLUE, font=font_sm)

    # Carrier / office / terminal (right block)
    draw.text((HDR_CARRIER_X, HDR_CARRIER_Y),
              _truncate(trip_info.get("carrier",       ""), 35),
              fill=TEXT_BLUE, font=font_sm)
    draw.text((HDR_CARRIER_X, HDR_OFFICE_Y),
              _truncate(trip_info.get("main_office",   ""), 35),
              fill=TEXT_BLUE, font=font_sm)
    draw.text((HDR_CARRIER_X, HDR_TERMINAL_Y),
              _truncate(trip_info.get("home_terminal", ""), 35),
              fill=TEXT_BLUE, font=font_sm)


def _draw_grid_lines(
    draw: ImageDraw.ImageDraw,
    sorted_events: list,
) -> None:
    """Draw horizontal status lines and vertical transition connectors."""
    for i, event in enumerate(sorted_events):
        t_start = event["time"]
        t_end   = sorted_events[i + 1]["time"] if i + 1 < len(sorted_events) else 24.0

        status = event["status"] if event["status"] in ROW_Y else "off_duty"
        x_start = _time_to_x(t_start)
        x_end   = _time_to_x(t_end)
        y       = ROW_Y[status]

        # Horizontal line for this duty period
        if x_end > x_start:
            draw.line([(x_start, y), (x_end, y)],
                      fill=LINE_COLOR, width=LINE_WIDTH)

        # Vertical connector at the transition point
        if i > 0:
            prev_status = sorted_events[i - 1]["status"]
            prev_status = prev_status if prev_status in ROW_Y else "off_duty"
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

    # Final dot at end of last segment (midnight)
    if sorted_events:
        last_status = sorted_events[-1]["status"]
        last_status = last_status if last_status in ROW_Y else "off_duty"
        last_y = ROW_Y[last_status]
        draw.ellipse(
            [(GRID_RIGHT - DOT_RADIUS, last_y - DOT_RADIUS),
             (GRID_RIGHT + DOT_RADIUS, last_y + DOT_RADIUS)],
            fill=DOT_COLOR,
        )


def _draw_hours_column(
    draw: ImageDraw.ImageDraw,
    totals: dict,
    font: ImageFont.FreeTypeFont,
) -> None:
    """Write H:MM totals in the narrow column to the right of the grid."""
    for status, row_y in ROW_Y.items():
        val  = totals.get(status, 0.0)
        text = _fmt_hours(val)
        draw.text((HOURS_COL_X, row_y - 4), text, fill=TEXT_BLACK, font=font)


def _draw_remarks_flags(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    sorted_events: list,
    font: ImageFont.FreeTypeFont,
) -> None:
    """
    For each duty-status change that has a remark or new location, draw:
      1. A short vertical drop-line from the grid row bottom to REMARKS_BASE_Y.
      2. A short horizontal tick at REMARKS_BASE_Y to mark the exact time.
      3. Vertical text (top-to-bottom, angle=-90°) centred on the flag x,
         starting just below REMARKS_BASE_Y and flowing downward into the
         remarks area.  Text is abbreviated and word-wrapped so each line is
         at most REMARKS_WRAP_CHARS characters wide.

    Labels that would overlap a previous label (x distance < REMARKS_MIN_TEXT_SPACING)
    have their text suppressed; the drop-line and tick are still drawn so the
    grid remains accurate.
    """
    last_text_x = None   # None = no label drawn yet; ensures first flag always renders

    for i, ev in enumerate(sorted_events):
        remark   = ev.get("remark",   "").strip()
        location = ev.get("location", "").strip()
        prev_loc = sorted_events[i - 1].get("location", "") if i > 0 else ""

        # Only draw a flag if there is a remark or the location changed
        if not remark and (i == 0 or location == prev_loc):
            continue

        t      = ev["time"]
        x      = _time_to_x(t)
        status = ev.get("status", "off_duty")
        status = status if status in ROW_BOTTOM else "off_duty"

        # 1. Vertical drop-line from grid row bottom to REMARKS_BASE_Y
        draw.line([(x, ROW_BOTTOM[status]), (x, REMARKS_BASE_Y)],
                  fill=LINE_COLOR, width=1)

        # 2. Short horizontal tick at REMARKS_BASE_Y to mark the time point
        draw.line([(x - 3, REMARKS_BASE_Y), (x + 3, REMARKS_BASE_Y)],
                  fill=LINE_COLOR, width=1)

        # 3. Vertical text (-90° = top-to-bottom), suppressed if too close to previous
        too_close = last_text_x is not None and abs(x - last_text_x) < REMARKS_MIN_TEXT_SPACING
        if not too_close:
            loc_short      = _abbrev_location(location)
            remark_wrapped = _wrap_remark(remark)
            text_parts     = [p for p in (loc_short, remark_wrapped) if p]
            if text_parts:
                text_str = "\n".join(text_parts)
                # Estimate original text block height (becomes rendered width after -90°
                # rotation) so we can centre the label horizontally on the flag x.
                n_lines    = text_str.count("\n") + 1
                line_px    = REMARKS_TEXT_SIZE + REMARKS_LINE_SPACING
                est_height = n_lines * line_px + REMARKS_TEXT_PADDING
                text_x = x - est_height // 2   # centre label on flag x
                text_y = REMARKS_BASE_Y + 3     # start just below the tick mark
                _paste_rotated_text(img, text_str, text_x, text_y, font, -90)
                last_text_x = x


def _draw_bottom_totals(
    draw: ImageDraw.ImageDraw,
    totals: dict,
    font_md: ImageFont.FreeTypeFont,
    font_lg: ImageFont.FreeTypeFont,
) -> None:
    """
    Draw driving / on-duty breakdown and the total on-duty hours inside
    a prominent red circle, matching the reference log style.
    """
    driving = totals.get("driving", 0.0)
    on_duty = totals.get("on_duty", 0.0)
    total   = driving + on_duty

    # Labels
    draw.text((TOTALS_DRV_X,  TOTALS_Y),
              f"Driving: {_fmt_hours(driving)}",
              fill=TEXT_BLACK, font=font_md)
    draw.text((TOTALS_DUTY_X, TOTALS_Y),
              f"On Duty (not driving): {_fmt_hours(on_duty)}",
              fill=TEXT_BLACK, font=font_md)

    # Total value (e.g. "10.5")
    total_str = f"{total:.1f}"
    draw.text((TOTALS_SUM_X, TOTALS_Y), total_str,
              fill=TEXT_BLACK, font=font_lg)

    # Red circle around the total number
    bbox = draw.textbbox((TOTALS_SUM_X, TOTALS_Y), total_str, font=font_lg)
    cx0 = bbox[0] - TOTAL_CIRCLE_PAD_X
    cy0 = bbox[1] - TOTAL_CIRCLE_PAD_Y
    cx1 = bbox[2] + TOTAL_CIRCLE_PAD_X
    cy1 = bbox[3] + TOTAL_CIRCLE_PAD_Y
    draw.ellipse([(cx0, cy0), (cx1, cy1)],
                 outline=CIRCLE_RED, width=CIRCLE_WIDTH)


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_log_image(
    day_info:    dict,
    trip_info:   dict,
    day_number:  int,
    total_days:  int,
) -> str:
    """
    Generate a single ELD daily log image drawn on the blank template and
    return it as a base64-encoded PNG string.

    Args:
        day_info:   dict with 'date_offset' (int) and 'events' (list of dicts
                    each having 'time', 'status', 'location', 'remark').
        trip_info:  trip metadata (carrier, locations, mileage, dates, etc.).
        day_number: 1-based day number within the trip.
        total_days: total days in the trip (for context only).

    Returns:
        Base64-encoded PNG string.
    """
    template_path = str(settings.LOG_TEMPLATE_PATH)
    img  = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_sm  = _load_font(7)
    font_md  = _load_font(8)
    font_lg  = _load_bold_font(9)
    font_rem = _load_font(REMARKS_TEXT_SIZE)   # larger font for remarks
    font_hrs = _load_font(HOURS_FONT_SIZE)     # small font for hours column

    events = day_info.get("events", [])

    # Header (always drawn, even on empty days)
    _draw_header(draw, day_info, trip_info, font_sm, font_md)

    if not events:
        return _image_to_base64(img)

    # Normalise: ensure the timeline starts at midnight (0:00)
    sorted_events = sorted(events, key=lambda e: e["time"])
    if sorted_events[0]["time"] > 0:
        sorted_events = [{
            "time":     0.0,
            "status":   "off_duty",
            "location": sorted_events[0].get("location", ""),
            "remark":   "",
        }] + sorted_events

    # Grid lines & dots
    _draw_grid_lines(draw, sorted_events)

    # Hours column
    from .hos_calculator import compute_daily_totals
    totals = compute_daily_totals(events)
    _draw_hours_column(draw, totals, font_hrs)

    # Remarks flags (rotated text) — pass img for alpha_composite
    _draw_remarks_flags(img, draw, sorted_events, font_rem)

    # Bottom summary + red circle
    _draw_bottom_totals(draw, totals, font_md, font_lg)

    return _image_to_base64(img)


def generate_all_logs(days: list, trip_info: dict) -> list:
    """
    Generate ELD log images for every day of a trip.

    Args:
        days:      list of day dicts from ``hos_calculator.build_trip_schedule``.
        trip_info: trip metadata dict.

    Returns:
        List of dicts: ``[{'day': int, 'date_offset': int,
                            'image_base64': str}, ...]``.
    """
    total = len(days)
    return [
        {
            "day":          i + 1,
            "date_offset":  day.get("date_offset", i),
            "image_base64": generate_log_image(day, trip_info, i + 1, total),
        }
        for i, day in enumerate(days)
    ]


