import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './RouteMap.css';

// Fix default Leaflet marker icons
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

const WAYPOINT_COLORS = {
  'Current Location': '#2b6cb0',
  Pickup: '#276749',
  Dropoff: '#c53030',
};

const WAYPOINT_LABELS = {
  'Current Location': 'S',
  Pickup: 'P',
  Dropoff: 'D',
};

const makeIcon = (color, label) =>
  L.divIcon({
    className: '',
    html: `<div style="
      background:${color};
      color:#fff;
      width:28px;height:28px;
      border-radius:50%;
      display:flex;align-items:center;justify-content:center;
      font-weight:700;font-size:13px;
      border:2px solid #fff;
      box-shadow:0 2px 6px rgba(0,0,0,0.4);
    ">${label}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });

const RouteMap = ({ routeData }) => {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const layerGroup = useRef(null);

  useEffect(() => {
    if (!mapRef.current) return;
    if (!mapInstance.current) {
      mapInstance.current = L.map(mapRef.current, { zoomControl: true }).setView(
        [39.5, -98.35],
        4
      );
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18,
      }).addTo(mapInstance.current);
      layerGroup.current = L.layerGroup().addTo(mapInstance.current);
    }
  }, []);

  useEffect(() => {
    if (!mapInstance.current || !routeData || !layerGroup.current) return;

    layerGroup.current.clearLayers();

    const { waypoints, geometry } = routeData;

    // Draw route polyline
    if (geometry && geometry.coordinates) {
      const latlngs = geometry.coordinates.map(([lng, lat]) => [lat, lng]);
      L.polyline(latlngs, {
        color: '#2b6cb0',
        weight: 4,
        opacity: 0.85,
      }).addTo(layerGroup.current);
    }

    // Add waypoint markers
    const bounds = [];
    (waypoints || []).forEach((wp) => {
      const color = WAYPOINT_COLORS[wp.label] || '#4a5568';
      const label = WAYPOINT_LABELS[wp.label] || '?';
      const icon = makeIcon(color, label);
      L.marker([wp.lat, wp.lon], { icon })
        .addTo(layerGroup.current)
        .bindPopup(
          `<div style="font-weight:600">${wp.label}</div><div>${wp.display_name}</div>`
        );
      bounds.push([wp.lat, wp.lon]);
    });

    if (bounds.length > 0) {
      mapInstance.current.fitBounds(bounds, { padding: [40, 40] });
    }
  }, [routeData]);

  const totalMiles = routeData?.total_distance_miles;
  const totalHours = routeData?.total_duration_hours;

  return (
    <div className="route-map">
      <h2 className="route-map__title">Route Map</h2>

      {routeData && (
        <div className="route-map__stats">
          <div className="route-map__stat">
            <span className="route-map__stat-label">Total Distance</span>
            <span className="route-map__stat-value">{totalMiles?.toLocaleString()} mi</span>
          </div>
          <div className="route-map__stat">
            <span className="route-map__stat-label">Drive Time</span>
            <span className="route-map__stat-value">
              {Math.floor(totalHours)}h {Math.round((totalHours % 1) * 60)}m
            </span>
          </div>
          <div className="route-map__legend">
            {Object.entries(WAYPOINT_COLORS).map(([label, color]) => (
              <span key={label} className="route-map__legend-item">
                <span
                  className="route-map__legend-dot"
                  style={{ background: color }}
                />
                {label}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="route-map__container" ref={mapRef} />

      {routeData?.legs && (
        <div className="route-map__legs">
          <h3>Legs</h3>
          {routeData.legs.map((leg, i) => (
            <div key={i} className="route-map__leg">
              <span className="route-map__leg-route">
                {leg.from_location} → {leg.to_location}
              </span>
              <span className="route-map__leg-detail">
                {(leg.distance_meters / 1609.34).toFixed(0)} mi ·{' '}
                {(leg.duration_seconds / 3600).toFixed(1)} hrs
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default RouteMap;
