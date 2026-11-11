
const BASE =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  const responseText = await response.text();

  let data = null;

  if (responseText) {
    try {
      data = JSON.parse(responseText);
    } catch {
      data = responseText;
    }
  }

  if (!response.ok) {
    const errorMessage =
      typeof data === "object" && data !== null
        ? data.detail || `API error: ${response.status}`
        : data || `API error: ${response.status}`;

    throw new Error(
      typeof errorMessage === "string"
        ? errorMessage
        : JSON.stringify(errorMessage)
    );
  }

  return data;
}

export const api = {
  // Health
  health: () => request("/health"),

  // Companies
  companies: () => request("/api/companies"),

  createCompany: (payload) =>
    request("/api/companies", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getCompany: (id) =>
    request(`/api/companies/${encodeURIComponent(id)}`),

  // Research
  startResearch: (id) =>
    request(`/api/companies/${encodeURIComponent(id)}/research`, {
      method: "POST",
    }),

  companyEvents: (id) =>
    request(`/api/companies/${encodeURIComponent(id)}/events`),

  companySources: (id) =>
    request(`/api/companies/${encodeURIComponent(id)}/sources`),

  // Feedback
  createFeedback: (payload) =>
    request("/api/feedback", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  feedbackAnalysis: (id) =>
    request(
      `/api/feedback/analysis/${encodeURIComponent(id)}`
    ),

  // Proposals
  analyzeProposal: (payload) =>
    request("/api/proposals/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
