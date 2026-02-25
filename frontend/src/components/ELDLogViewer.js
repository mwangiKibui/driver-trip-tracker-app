import React, { useState } from 'react';
import './ELDLogViewer.css';

const STATUS_COLORS = {
  off_duty: '#4a5568',
  sleeper_berth: '#6b46c1',
  driving: '#2b6cb0',
  on_duty: '#276749',
};

const STATUS_LABELS = {
  off_duty: 'Off Duty',
  sleeper_berth: 'Sleeper Berth',
  driving: 'Driving',
  on_duty: 'On Duty (Not Driving)',
};

const formatHours = (h) => {
  const hrs = Math.floor(h);
  const mins = Math.round((h - hrs) * 60);
  return `${hrs}h ${mins.toString().padStart(2, '0')}m`;
};

const DaySchedule = ({ day }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="eld-schedule__day">
      <button
        className="eld-schedule__day-header"
        onClick={() => setExpanded((e) => !e)}
      >
        <span>Day {day.day} — Events</span>
        <span className="eld-schedule__chevron">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded && (
        <table className="eld-schedule__table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Status</th>
              <th>Location</th>
              <th>Remark</th>
            </tr>
          </thead>
          <tbody>
            {day.events.map((ev, i) => {
              const hrs = Math.floor(ev.time);
              const mins = Math.round((ev.time - hrs) * 60);
              const timeStr = `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
              const next = day.events[i + 1];
              const endTime = next ? next.time : 24;
              const duration = endTime - ev.time;
              return (
                <tr key={i}>
                  <td>{timeStr}</td>
                  <td>
                    <span
                      className="eld-schedule__badge"
                      style={{ background: STATUS_COLORS[ev.status] }}
                    >
                      {STATUS_LABELS[ev.status] || ev.status}
                    </span>
                  </td>
                  <td>{ev.location}</td>
                  <td>{ev.remark || `(${formatHours(duration)})`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
};

const ELDLogViewer = ({ logs, schedule }) => {
  const [activeDay, setActiveDay] = useState(0);

  if (!logs || logs.length === 0) return null;

  const currentLog = logs[activeDay];
  const currentSchedule = schedule?.[activeDay];

  return (
    <div className="eld-viewer">
      <h2 className="eld-viewer__title">ELD Daily Log Sheets</h2>
      <p className="eld-viewer__subtitle">
        {logs.length} log sheet{logs.length > 1 ? 's' : ''} generated
      </p>

      {/* Day tabs */}
      <div className="eld-viewer__tabs">
        {logs.map((log, i) => (
          <button
            key={i}
            className={`eld-viewer__tab ${activeDay === i ? 'eld-viewer__tab--active' : ''}`}
            onClick={() => setActiveDay(i)}
          >
            Day {log.day}
          </button>
        ))}
      </div>

      {/* Log image */}
      <div className="eld-viewer__log-wrapper">
        <img
          src={`data:image/png;base64,${currentLog.image_base64}`}
          alt={`ELD Log Day ${currentLog.day}`}
          className="eld-viewer__log-image"
        />
      </div>

      {/* Daily totals */}
      {currentSchedule?.totals && (
        <div className="eld-viewer__totals">
          {Object.entries(STATUS_LABELS).map(([key, label]) => {
            const hrs = currentSchedule.totals[key] || 0;
            return (
              <div key={key} className="eld-viewer__total-item">
                <span
                  className="eld-viewer__total-bar"
                  style={{
                    background: STATUS_COLORS[key],
                    width: `${(hrs / 24) * 100}%`,
                  }}
                />
                <span className="eld-viewer__total-label">{label}</span>
                <span className="eld-viewer__total-value">{formatHours(hrs)}</span>
              </div>
            );
          })}
          <div className="eld-viewer__total-combined">
            Total On-Duty:{' '}
            <strong>
              {formatHours(
                (currentSchedule.totals.driving || 0) +
                  (currentSchedule.totals.on_duty || 0)
              )}
            </strong>
          </div>
        </div>
      )}

      {/* Event schedule */}
      {currentSchedule && <DaySchedule day={currentSchedule} />}
    </div>
  );
};

export default ELDLogViewer;
