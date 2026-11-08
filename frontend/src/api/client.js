const BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `API error: ${response.status}`);
  }
  return response.json();
}

export const api = {
  health: () => request('/health'),
  companies: () => request('/api/companies'),
  createCompany: (payload) => request('/api/companies', { method: 'POST', body: JSON.stringify(payload) }),
  companyEvents: (id) => request(`/api/companies/${id}/events`),
  companySources: (id) => request(`/api/companies/${id}/sources`),
};
