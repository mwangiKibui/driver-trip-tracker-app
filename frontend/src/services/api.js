import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

export const planTrip = async (tripData) => {
  const response = await axios.post(`${API_BASE}/trip/plan/`, tripData);
  return response.data;
};
