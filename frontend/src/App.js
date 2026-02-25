import React, { useState } from 'react';
import TripForm from './components/TripForm';
import RouteMap from './components/RouteMap';
import ELDLogViewer from './components/ELDLogViewer';
import { planTrip } from './services/api';
import './App.css';

function App() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const handleSubmit = async (formData) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await planTrip(formData);
      setResult(data);
    } catch (err) {
      const msg =
        err?.response?.data?.error ||
        err?.message ||
        'An unexpected error occurred. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__header-inner">
          <span className="app__logo">🚛</span>
          <div>
            <h1 className="app__title">Driver Trip Tracker</h1>
            <p className="app__tagline">
              Route planning &amp; ELD log generation for truck drivers
            </p>
          </div>
        </div>
      </header>

      <main className="app__main">
        <section className="app__form-section">
          <TripForm onSubmit={handleSubmit} loading={loading} />
        </section>

        {error && (
          <div className="app__error">
            <strong>Error:</strong> {error}
          </div>
        )}

        {loading && (
          <div className="app__loading">
            <div className="app__spinner" />
            <p>Planning route and generating ELD logs…</p>
          </div>
        )}

        {result && (
          <section className="app__results">
            <RouteMap routeData={result.route} />
            <ELDLogViewer logs={result.logs} schedule={result.schedule} />
          </section>
        )}
      </main>

      <footer className="app__footer">
        <p>
          Powered by{' '}
          <a href="https://www.openstreetmap.org" target="_blank" rel="noreferrer">
            OpenStreetMap
          </a>{' '}
          &amp;{' '}
          <a href="http://project-osrm.org" target="_blank" rel="noreferrer">
            OSRM
          </a>
        </p>
      </footer>
    </div>
  );
}

export default App;
