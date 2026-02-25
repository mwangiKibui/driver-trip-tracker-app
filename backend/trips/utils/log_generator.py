"""
ELD (Electronic Logging Device) Daily Log Generator.

Draws driver daily log entries on the blank template image using PIL.

Template image: files/template/blank-driver-log.png (513×518 pixels)

The template is scaled up to GRID_CANVAS_W=750 px so that grid content is
clearly visible.  An additional 100 px of white canvas is appended to the
right for the hours column, giving OUTPUT_WIDTH=850 px total.

All template-relative coordinates are expressed in original template pixels
and converted to output pixels via _s() using SCALE = GRID_CANVAS_W / TEMPLATE_W.

Grid coordinate reference (original template pixels → scaled output pixels):
  - Grid left edge  (midnight start): 56  → GRID_LEFT  = _s(56)  ≈ 82
  - Grid right edge (midnight end):   491 → GRID_RIGHT = _s(491) ≈ 718
  - Grid width for 24 hours:          435 → GRID_WIDTH ≈ 636
  - Pixels per hour (scaled):         GRID_WIDTH / 24 ≈ 26.5

  Duty-status row centre Y positions (original → scaled):
  - Off Duty:        192 → ROW_Y["off_duty"]      ≈ 281
  - Sleeper Berth:   209 → ROW_Y["sleeper_berth"] ≈ 306
  - Driving:         226 → ROW_Y["driving"]       ≈ 330
  - On Duty (not):   243 → ROW_Y["on_duty"]       ≈ 355

Brackets:
  - For each on_duty period a U-shaped bracket (cup) is drawn in the REMARKS
    area at REMARKS_BASE_Y — right where the vertical drop-lines end — so the
    bracket is visually connected to the flag lines, not inside the grid rows.
      Top bar:    horizontal line at REMARKS_BASE_Y spanning t_start → t_end.
      Arms:       descend BRACKET_ARM px below the top bar at each end.
      Bottom bar: horizontal line connecting both arm bottoms.
  - Line weight = LINE_WIDTH so the bracket is as prominent as the grid lines.

Remarks layout:
  - REMARKS_BASE_Y ≈ 373: drop-lines end + diagonal tick starts here
  - Tick angle and text angle are matched so the label appears to "move with" the line:
      • x_gap ≥ MIN_SPACING: 45° tick + -45° text (gentle diagonal)
      • x_gap < MIN_SPACING:  10° tick + -10° text (nearly horizontal)
  - Very-close labels (x_gap < MIN_SPACING/2) alternate Y by REMARKS_Y_STAGGER
    so nearly-horizontal text blocks do not overlap.
  - No label is ever suppressed.
  - Totals drawn below remarks area at y≈527 / y≈550
"""

import io
import base64
import textwrap
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings

# ── Canvas / Scaling ──────────────────────────────────────────────────────────
TEMPLATE_W    = 513   # original blank-driver-log.png width  (px)
TEMPLATE_H    = 518   # original blank-driver-log.png height (px)

# The template is scaled up to GRID_CANVAS_W so that the grid content is larger
# and more legible.  An extra margin is appended on the right for the hours column.
GRID_CANVAS_W = 750   # width the template is scaled to fill (px)
SCALE         = GRID_CANVAS_W / TEMPLATE_W   # ≈ 1.462 – applied to every template coord
OUTPUT_WIDTH  = GRID_CANVAS_W + 100          # total canvas width (extra space for hours col)


def _s(v: float) -> int:
    """Scale an original-template pixel coordinate to the output canvas."""
    return int(round(v * SCALE))


# ── Grid constants ─────────────────────────────────────────────────────────────
GRID_LEFT  = _s(56)    # x pixel for hour 0 (midnight start)
GRID_RIGHT = _s(491)   # x pixel for hour 24 (midnight end) – template's printed border
                       #   status lines stop exactly here, leaving a clear gap before
                       #   the hours column which lives at x ≥ GRID_CANVAS_W + gap
GRID_WIDTH = GRID_RIGHT - GRID_LEFT   # pixels = 24 hours

# Duty-status row centre Y positions
ROW_Y = {
    "off_duty":      _s(192),
    "sleeper_berth": _s(209),
    "driving":       _s(226),
    "on_duty":       _s(243),
}

# Bottom edge of each duty-status row (start of remarks drop-lines)
ROW_BOTTOM = {
    "off_duty":      _s(201),
    "sleeper_berth": _s(218),
    "driving":       _s(235),
    "on_duty":       _s(252),
}

# ── Colours ────────────────────────────────────────────────────────────────────
LINE_COLOR    = (0,   0,   0)    # grid lines / connectors
DOT_COLOR     = (180, 0,   0)    # status-change dots (dark red)
TEXT_BLACK    = (0,   0,   0)    # body text
TEXT_BLUE     = (0,   0, 180)    # header fill text
CIRCLE_RED    = (200, 0,   0)    # total-hours circle outline (red)

# ── Line weights (scaled proportionally) ──────────────────────────────────────
LINE_WIDTH    = max(2, _s(2))    # ≈ 3
DOT_RADIUS    = max(3, _s(3))    # ≈ 4
CIRCLE_WIDTH  = max(2, _s(2))    # ≈ 3

# ── Header field positions (all scaled from original template coordinates) ─────
# Date values sit ABOVE the underline; sub-label centres at x≈187/227/271.
HDR_DATE_Y       = _s(7)     # y for date values
HDR_DATE_MONTH_X = _s(182)   # x for month value
HDR_DATE_DAY_X   = _s(223)   # x for day value
HDR_DATE_YEAR_X  = _s(255)   # x for year value

# "From:" label ends at x≈86; "To:" label ends at x≈270.
HDR_FROM_TO_Y    = _s(37)    # y for From / To row
HDR_FROM_X       = _s(90)    # x for "from" value
HDR_TO_X         = _s(278)   # x for "to"   value

HDR_MILES_Y      = _s(72)    # y for mileage row
HDR_MILES_DRV_X  = _s(85)    # x for "Total Miles Driving Today"
HDR_MILES_TOT_X  = _s(155)   # x for "Total Mileage Today"

HDR_TRUCK_X      = _s(63)    # x for truck / trailer numbers
HDR_TRUCK_Y      = _s(105)   # y for truck / trailer numbers

# Right block (carrier / office / terminal): values sit ABOVE each underline.
HDR_CARRIER_X    = _s(234)   # x for carrier / office / terminal (right block)
HDR_CARRIER_Y    = _s(68)    # y for carrier name
HDR_OFFICE_Y     = _s(88)    # y for main office address
HDR_TERMINAL_Y   = _s(109)   # y for home terminal address

# ── Hours column ───────────────────────────────────────────────────────────────
# Placed in the expanded canvas area to the right of GRID_CANVAS_W, giving a
# clear visual gap between the midnight status-line end and the H:MM values.
HOURS_COL_X      = GRID_CANVAS_W + 8   # 758 px – well to the right of GRID_RIGHT≈718
HOURS_FONT_SIZE  = _s(7)               # ≈ 10 pt – legible at the larger canvas scale

# ── Remarks section ────────────────────────────────────────────────────────────
REMARKS_BASE_Y           = _s(255)  # y where vertical drop-lines end (≈373)
REMARKS_TEXT_SIZE        = 7        # font size for rotated remarks text (readable at 850px canvas)
REMARKS_WRAP_CHARS       = 10       # max chars per line before word-wrapping (narrow blocks)
REMARKS_MIN_TEXT_SPACING = _s(44)   # ≈ 64 px – threshold for switching to near-overlap geometry
# Three-level Y cycle for very-close labels (x_gap < MIN_SPACING/2 ≈32px).
# Cycling over 3 distinct offsets prevents any two consecutive close labels
# from sharing the same baseline even when 3+ events cluster together.
REMARKS_Y_OFFSETS        = (0, 14, 28)  # Y offsets for 3-level stagger cycle (px)

# Tick geometry — tick line direction matches the text angle so the label
# appears to "move with" the diagonal line:
#   Default (enough space): 45° tick  →  -45° text (gentle diagonal, text rises up-right)
#   Near-overlap:           10° tick  →  -10° text (nearly horizontal, compact vertical footprint)
TICK_DEFAULT_DX  = 12   # 45° tick: right component (px)
TICK_DEFAULT_DY  = 12   # 45° tick: down  component (px)
TICK_NEAR_DX     = 20   # ~10° tick: right component (tan10°≈0.18 → dy≈4)
TICK_NEAR_DY     = 4    # ~10° tick: down  component (px)

# Text rotation angles (PIL: negative = clockwise from horizontal)
REMARKS_ANGLE      = -45   # default: 45° from horizontal (text rises up-right)
REMARKS_ANGLE_NEAR = -10   # near-overlap: 10° from horizontal (nearly horizontal)

# ── Bracket marks ──────────────────────────────────────────────────────────────
# For on_duty (non-driving) periods the truck is stationary.  A bracket (cup)
# mark ⌐...¬ is drawn in the remarks area (below the grid) for each such period.
# The bracket is placed at REMARKS_BASE_Y — exactly where the vertical drop-lines
# end — so the bracket is visually "connected to" and "hanging from" the flag lines.
# The bracket has three sides (U / cup shape opening downward):
#   Top bar:    horizontal line at REMARKS_BASE_Y spanning t_start → t_end —
#               connects the two drop-lines and shows the stationary time span.
#   Arms:       short vertical lines descending from the top bar at each end.
#   Bottom bar: horizontal line connecting both arm bottoms.
BRACKET_ARM = max(8, _s(14))  # depth of arms below REMARKS_BASE_Y (px)

# ── Bottom totals ──────────────────────────────────────────────────────────────
# Two-line layout in the remarks free-write area, placed BELOW the remarks text
# band.  Since all remarks labels now anchor at REMARKS_TEXT_Y≈378 and rise
# UPWARD, the totals only need to clear the small area just below REMARKS_TEXT_Y.
#
# TOTALS_DRV_X is chosen to clear the pre-printed "Shipping Documents:" label
# which originally occupies x≈22–100 (scaled to x≈32–146).
TOTALS_Y         = _s(360)   # y of line 1 (≈527 px – below remarks anchor)
TOTALS_DRV_X     = _s(130)   # x for "Driving: ..." (right of pre-printed label)
TOTALS_DUTY_X    = _s(197)   # x for "On Duty (not driving): ..."
TOTALS_TOTAL_Y   = _s(376)   # y of line 2 (circled total, ≈550 px)
TOTALS_SUM_X     = _s(130)   # x for circled total (left-aligned with "Driving:")

# Red circle around the on-duty total
TOTAL_CIRCLE_PAD_X = _s(8)   # horizontal padding inside circle
TOTAL_CIRCLE_PAD_Y = _s(4)   # vertical padding inside circle


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


def _draw_brackets(
    draw: ImageDraw.ImageDraw,
    sorted_events: list,
) -> None:
    """
    Draw U-shaped bracket (cup) marks in the REMARKS area for each on_duty period.

    During on_duty (non-driving work) periods the truck is stationary at a
    location.  A bracket ⌐___¬ is drawn in the remarks area (below the grid)
    at REMARKS_BASE_Y — exactly where the vertical drop-lines end — so the
    bracket appears "connected to" and "hanging from" the flag lines:
      - Top bar:    horizontal line at REMARKS_BASE_Y spanning t_start → t_end.
      - Left  arm:  vertical line descending from the top bar at t_start.
      - Right arm:  vertical line descending from the top bar at t_end.
      - Bottom bar: horizontal line connecting both arm bottoms.

    Line weight matches LINE_WIDTH so the bracket is as prominent as the grid.
    This matches the "bracket / cup" notation described in FMCSA logbook
    training: the bracket denotes the section of time the truck did not move.
    """
    y_top    = REMARKS_BASE_Y
    y_bottom = y_top + BRACKET_ARM

    for i, ev in enumerate(sorted_events):
        if ev.get("status") != "on_duty":
            continue

        t_start = ev["time"]
        t_end   = sorted_events[i + 1]["time"] if i + 1 < len(sorted_events) else 24.0

        x_start = _time_to_x(t_start)
        x_end   = _time_to_x(t_end)

        if x_end <= x_start + 2:   # too narrow to be visible
            continue

        # Top bar: horizontal line at REMARKS_BASE_Y — connects to the drop-lines
        draw.line([(x_start, y_top), (x_end,    y_top)],    fill=LINE_COLOR, width=LINE_WIDTH)
        # Left arm, right arm, bottom bar
        draw.line([(x_start, y_top), (x_start,  y_bottom)], fill=LINE_COLOR, width=LINE_WIDTH)
        draw.line([(x_end,   y_top), (x_end,    y_bottom)], fill=LINE_COLOR, width=LINE_WIDTH)
        draw.line([(x_start, y_bottom), (x_end, y_bottom)], fill=LINE_COLOR, width=LINE_WIDTH)


def _draw_remarks_flags(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    sorted_events: list,
    font: ImageFont.FreeTypeFont,
) -> None:
    """
    For each duty-status change that has a remark or new location, draw:
      1. A vertical drop-line from the grid row bottom to REMARKS_BASE_Y.
      2. A diagonal tick at REMARKS_BASE_Y whose angle matches the text angle,
         so the label visually "moves with" the flag line.
      3. Rotated text anchored at the tick endpoint.

    Adaptive geometry (tick angle and text angle are always matched):
      - Default (x_gap ≥ MIN_SPACING):  45° tick + -45° text (gentle diagonal).
      - Near    (x_gap < MIN_SPACING):  10° tick + -10° text (nearly horizontal).
        Very-close labels (x_gap < MIN_SPACING/2) additionally alternate Y by
        REMARKS_Y_STAGGER so the nearly-horizontal text blocks do not overlap.
      - No label is ever suppressed — all remarks are always rendered.
    """
    last_x          = -REMARKS_MIN_TEXT_SPACING * 2
    stagger_idx     = 0     # cycles through REMARKS_Y_OFFSETS for very-close labels
    last_flagged_loc = ""   # last location that was printed; omit location if unchanged

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

        # 2. Diagonal tick — angle matches the text angle so label follows line
        x_gap = abs(x - last_x)
        if x_gap < REMARKS_MIN_TEXT_SPACING:
            tick_dx, tick_dy = TICK_NEAR_DX, TICK_NEAR_DY
            angle = REMARKS_ANGLE_NEAR     # -10°: nearly horizontal
        else:
            tick_dx, tick_dy = TICK_DEFAULT_DX, TICK_DEFAULT_DY
            angle = REMARKS_ANGLE          # -45°: gentle diagonal

        draw.line([(x, REMARKS_BASE_Y), (x + tick_dx, REMARKS_BASE_Y + tick_dy)],
                  fill=LINE_COLOR, width=1)

        # 3. Rotated text anchored at the tick endpoint.
        #    Only include the location line when the driver has moved to a new
        #    location since the last flagged event — repeating the same city name
        #    at consecutive stops wastes space and causes overlap.
        loc_short   = _abbrev_location(location)
        show_loc    = loc_short != last_flagged_loc   # True when location changed
        loc_wrapped = _wrap_remark(loc_short) if show_loc else ""
        remark_wrapped = _wrap_remark(remark)
        text_parts  = [p for p in (loc_wrapped, remark_wrapped) if p]
        if not text_parts:
            last_flagged_loc = loc_short
            last_x = x
            continue

        text_str = "\n".join(text_parts)

        # For very-close labels at -10° (nearly horizontal), cycle through 3
        # distinct Y offsets so even 3 consecutive close events are separated.
        if x_gap < REMARKS_MIN_TEXT_SPACING / 2:
            y_extra     = REMARKS_Y_OFFSETS[stagger_idx % len(REMARKS_Y_OFFSETS)]
            stagger_idx += 1
        else:
            y_extra     = 0
            stagger_idx = 0

        text_x = x + tick_dx
        text_y = REMARKS_BASE_Y + tick_dy + y_extra

        _paste_rotated_text(img, text_str, text_x, text_y, font, angle)
        last_flagged_loc = loc_short
        last_x = x


def _draw_bottom_totals(
    draw: ImageDraw.ImageDraw,
    totals: dict,
    font_md: ImageFont.FreeTypeFont,
    font_lg: ImageFont.FreeTypeFont,
) -> None:
    """
    Draw driving / on-duty breakdown and the total on-duty hours inside
    a prominent red circle, matching the reference log style.

    Layout (two lines to prevent collision):
      Line 1 (TOTALS_Y):       "Driving: H:MM    On Duty (not driving): H:MM"
      Line 2 (TOTALS_TOTAL_Y): "[Total]"  (circled, left-aligned under "Driving:")
    """
    driving = totals.get("driving", 0.0)
    on_duty = totals.get("on_duty", 0.0)
    total   = driving + on_duty

    # Line 1 – Driving and On Duty labels
    draw.text((TOTALS_DRV_X,  TOTALS_Y),
              f"Driving: {_fmt_hours(driving)}",
              fill=TEXT_BLACK, font=font_md)
    draw.text((TOTALS_DUTY_X, TOTALS_Y),
              f"On Duty (not driving): {_fmt_hours(on_duty)}",
              fill=TEXT_BLACK, font=font_md)

    # Line 2 – Circled total value (left-aligned, own line, no collision risk)
    total_str = f"{total:.1f}"
    draw.text((TOTALS_SUM_X, TOTALS_TOTAL_Y), total_str,
              fill=TEXT_BLACK, font=font_lg)

    # Red circle around the total number
    bbox = draw.textbbox((TOTALS_SUM_X, TOTALS_TOTAL_Y), total_str, font=font_lg)
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
    img = Image.open(template_path).convert("RGB")

    # Scale the template up to GRID_CANVAS_W so all grid content is larger and
    # more legible.  Height is scaled by the same factor to preserve proportions.
    new_h = int(round(img.height * SCALE))
    img = img.resize((GRID_CANVAS_W, new_h), Image.LANCZOS)

    # Append a white strip on the right for the hours column and totals area.
    if img.width < OUTPUT_WIDTH:
        expanded = Image.new("RGB", (OUTPUT_WIDTH, new_h), (255, 255, 255))
        expanded.paste(img, (0, 0))
        img = expanded

    draw = ImageDraw.Draw(img)

    # Font sizes are scaled proportionally so text matches the enlarged grid.
    font_sm  = _load_font(_s(7))
    font_md  = _load_font(_s(8))
    font_lg  = _load_bold_font(_s(9))
    font_rem = _load_font(REMARKS_TEXT_SIZE)
    font_hrs = _load_font(HOURS_FONT_SIZE)

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

    # Bracket marks on driving row for on_duty (stationary truck) periods
    _draw_brackets(draw, sorted_events)

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


