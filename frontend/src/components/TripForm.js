import React, { useState } from 'react';
import './TripForm.css';

const TripForm = ({ onSubmit, loading }) => {
  const [formData, setFormData] = useState({
    current_location: '',
    pickup_location: '',
    dropoff_location: '',
    current_cycle_used: '',
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const data = {
      ...formData,
      current_cycle_used: parseFloat(formData.current_cycle_used) || 0,
    };
    onSubmit(data);
  };

  return (
    <form className="trip-form" onSubmit={handleSubmit}>
      <h2 className="trip-form__title">Trip Details</h2>

      <div className="trip-form__field">
        <label htmlFor="current_location">Current Location</label>
        <input
          id="current_location"
          name="current_location"
          type="text"
          placeholder="e.g. Bakersfield, California"
          value={formData.current_location}
          onChange={handleChange}
          required
        />
      </div>

      <div className="trip-form__field">
        <label htmlFor="pickup_location">Pickup Location</label>
        <input
          id="pickup_location"
          name="pickup_location"
          type="text"
          placeholder="e.g. Los Angeles, California"
          value={formData.pickup_location}
          onChange={handleChange}
          required
        />
      </div>

      <div className="trip-form__field">
        <label htmlFor="dropoff_location">Dropoff Location</label>
        <input
          id="dropoff_location"
          name="dropoff_location"
          type="text"
          placeholder="e.g. Reno, Nevada"
          value={formData.dropoff_location}
          onChange={handleChange}
          required
        />
      </div>

      <div className="trip-form__field">
        <label htmlFor="current_cycle_used">Current Cycle Used (Hrs)</label>
        <input
          id="current_cycle_used"
          name="current_cycle_used"
          type="number"
          min="0"
          max="70"
          step="0.5"
          placeholder="e.g. 36"
          value={formData.current_cycle_used}
          onChange={handleChange}
          required
        />
        <span className="trip-form__hint">Hours used in 70-hr/8-day cycle (0–70)</span>
      </div>

      <button
        type="submit"
        className="trip-form__submit"
        disabled={loading}
      >
        {loading ? 'Planning Route…' : 'Plan Trip'}
      </button>
    </form>
  );
};

export default TripForm;
