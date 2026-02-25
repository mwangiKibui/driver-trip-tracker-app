# Driver Trip Tracker App

A full-stack application for truck drivers to plan trips and generate ELD (Electronic Logging Device) daily log sheets, built with **React** (frontend) and **Django** (backend).

---

## Features

- **Trip Planning**: Enter current location, pickup location, dropoff location, and current cycle hours used.
- **Route Map**: Interactive map (Leaflet + OpenStreetMap) showing the driving route with waypoints.
- **HOS Compliance**: Automatically applies FMCSA Hours of Service rules:
  - 11-hour driving limit per shift
  - 14-hour on-duty window
  - 30-minute mandatory break after 8 hours of driving
  - 10-hour minimum off-duty between shifts
  - 70-hour/8-day cycle tracking
- **ELD Log Sheets**: Generates filled-in driver daily log sheets (drawn on the official blank template), one per day of the trip.

---

## Tech Stack

| Layer    | Technology                                         |
|----------|----------------------------------------------------|
| Frontend | React, Leaflet (react-leaflet), Axios              |
| Backend  | Django, Django REST Framework, Pillow              |
| Maps     | OpenStreetMap tiles (free)                         |
| Routing  | OSRM public API (free, `router.project-osrm.org`)  |
| Geocoding| Nominatim API (free, `nominatim.openstreetmap.org`)|

---

## Project Structure

```
driver-trip-tracker-app/
├── files/
│   ├── template/
│   │   └── blank-driver-log.png        # Blank ELD log template
│   └── processed/                      # Reference processed log examples
├── backend/                            # Django project
│   ├── backend/                        # Django settings, URLs
│   ├── trips/                          # Main app
│   │   ├── utils/
│   │   │   ├── geocoder.py             # Nominatim geocoding
│   │   │   ├── router.py               # OSRM route calculation
│   │   │   ├── hos_calculator.py       # HOS rules engine
│   │   │   └── log_generator.py        # PIL-based ELD log drawing
│   │   ├── views.py                    # REST API view
│   │   └── urls.py
│   └── requirements.txt
└── frontend/                           # React project
    └── src/
        ├── components/
        │   ├── TripForm.js             # Input form
        │   ├── RouteMap.js             # Leaflet map
        │   └── ELDLogViewer.js         # Log sheet viewer
        ├── services/
        │   └── api.js                  # Axios API calls
        └── App.js
```

---

## Getting Started

### Backend

```bash
cd backend

# Install Python dependencies
pip install -r requirements.txt

# Apply migrations (SQLite, no configuration needed)
python manage.py migrate

# Start the development server
python manage.py runserver 8000
```

The API will be available at `http://localhost:8000/api/`.

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm start
```

The app will be available at `http://localhost:3000`.

> **Note**: The frontend expects the backend at `http://localhost:8000/api` by default.  
> To customise, create `frontend/.env` with:  
> ```
> REACT_APP_API_URL=http://localhost:8000/api
> ```

---

## API Reference

### `POST /api/trip/plan/`

**Request body (JSON):**

```json
{
  "current_location": "Chicago, IL",
  "pickup_location": "Milwaukee, WI",
  "dropoff_location": "Minneapolis, MN",
  "current_cycle_used": 20.5
}
```

**Response (JSON):**

```json
{
  "route": {
    "waypoints": [...],
    "geometry": { "type": "LineString", "coordinates": [...] },
    "legs": [...],
    "total_distance_miles": 410.2,
    "total_duration_hours": 6.8
  },
  "schedule": [
    {
      "day": 1,
      "date_offset": 0,
      "events": [
        { "time": 0.0, "status": "off_duty", "location": "Chicago, IL", "remark": "" },
        { "time": 6.0, "status": "on_duty", "location": "Chicago, IL", "remark": "Pre-trip inspection" },
        ...
      ],
      "totals": { "off_duty": 12.0, "sleeper_berth": 0.0, "driving": 11.0, "on_duty": 1.0 }
    }
  ],
  "logs": [
    { "day": 1, "date_offset": 0, "image_base64": "iVBOR..." },
    ...
  ]
}
```

---

## ELD Log Generation

The log generator draws on the official `blank-driver-log.png` template using PIL (Pillow):

- **Grid lines**: Horizontal lines drawn through each duty-status row for the duration of that status.
- **Connectors**: Vertical lines at status-change times connecting the rows.
- **Red dots**: Mark each status-change point.
- **Remarks flags**: Diagonal flag lines with location and remark text at each status change.
- **Hours totals**: Written in the right-side hours column.
- **Summary**: Driving + on-duty total shown at the bottom.

### Duty Status Rows (Grid Y positions)
| Row | Status | Y centre (px) |
|-----|--------|----------------|
| 1 | Off Duty | 192 |
| 2 | Sleeper Berth | 209 |
| 3 | Driving | 226 |
| 4 | On Duty (not driving) | 243 |

### Time → X pixel mapping
```
x = 56 + (hour / 24) × 435
```
- Midnight (0h): x = 56
- Noon (12h): x = 273
- Midnight (24h): x = 491

---

## HOS Rules Applied

| Rule | Limit |
|------|-------|
| Driving per shift | 11 hours |
| On-duty window | 14 hours |
| Break required after | 8 hours driving |
| Break duration | 30 minutes |
| Off-duty between shifts | 10 hours |
| Cycle limit | 70 hours / 8 days |

---

## External APIs Used (all free)

| Service | URL | Purpose |
|---------|-----|---------|
| Nominatim | `nominatim.openstreetmap.org` | Geocoding location strings |
| OSRM | `router.project-osrm.org` | Driving route & duration |
| OpenStreetMap | `tile.openstreetmap.org` | Map tiles (frontend) |
