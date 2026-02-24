import { render, screen } from '@testing-library/react';
import App from './App';

test('renders Driver Trip Tracker heading', () => {
  render(<App />);
  const heading = screen.getByText(/Driver Trip Tracker/i);
  expect(heading).toBeInTheDocument();
});

test('renders trip form fields', () => {
  render(<App />);
  expect(screen.getByLabelText(/Current Location/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/Pickup Location/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/Dropoff Location/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/Current Cycle Used/i)).toBeInTheDocument();
});
