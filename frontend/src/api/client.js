const BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function request(path, options = {}) {
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
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
    const detail = typeof data === 'object' && data !== null
      ? data.detail || `API error: ${response.status}`
      : data || `API error: ${response.status}`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }

  return data;
}

const companyPath = (id) => `/api/companies/${encodeURIComponent(id)}`;

export const api = {
  health: () => request('/health'),
  companies: () => request('/api/companies'),
  createCompany: (payload) => request('/api/companies', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  getCompany: (id) => request(companyPath(id)),
  companyEvents: (id) => request(`${companyPath(id)}/events`),
  companySources: (id) => request(`${companyPath(id)}/sources`),
  companyInternalSources: (id) => request(`${companyPath(id)}/internal-sources`),
  companyKnowledgeItems: (id, query = '', includeAuthorizedInternal = false) => {
    const params = new URLSearchParams();
    if (query) params.set('query', query);
    if (includeAuthorizedInternal) params.set('include_authorized_internal', 'true');
    const suffix = params.toString() ? `?${params.toString()}` : '';
    return request(`${companyPath(id)}/knowledge-items${suffix}`);
  },
  companyResearchStats: (id) => request(`${companyPath(id)}/research-stats`),
  importInternalSource: (id, file, { author = '', recordedAt = '', isSynthetic = false } = {}) => {
    const form = new FormData();
    form.append('file', file);
    if (author) form.append('author', author);
    if (recordedAt) form.append('recorded_at', recordedAt);
    form.append('is_synthetic', String(isSynthetic));
    return request(`${companyPath(id)}/internal-sources`, {
      method: 'POST',
      body: form,
    });
  },
  companyKnowledgeGraph: (id) => request(`${companyPath(id)}/knowledge-graph`),
  companyFeedbackAnalysis: (id) => request(`/api/feedback/analysis/${encodeURIComponent(id)}`),
  companyFeedbackTrends: (id) => request(`/api/feedback/trends/${encodeURIComponent(id)}`),
  companyFeedbackRecords: async (id) => {
    const result = await request(`${companyPath(id)}/feedback`);
    return Array.isArray(result) ? result : Array.isArray(result?.items) ? result.items : null;
  },
  companyIngestionStatus: (id, includeAuthorizedInternal = false) => request(
    `/api/ingestion/companies/${encodeURIComponent(id)}/status${includeAuthorizedInternal ? '?include_authorized_internal=true' : ''}`,
  ),
  researchCompany: (id, maxPages = 12, searchDepth = 4, background = false) => request(
    `${companyPath(id)}/research?max_pages=${maxPages}&search_depth=${searchDepth}&background=${background}`,
    { method: 'POST' },
  ),
  processCompanySources: (id, sourceIds = null, includeAuthorizedInternal = false) => request(
    `/api/ingestion/companies/${encodeURIComponent(id)}/process?include_authorized_internal=${includeAuthorizedInternal}`,
    {
      method: 'POST',
      body: JSON.stringify({ source_ids: sourceIds }),
    },
  ),
  submitFeedback: (payload) => request('/api/feedback', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  createProposal: (payload) => request('/api/proposals', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  answerQuestion: (payload) => request('/api/ai/answer', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  analyzeProposal: (payload) => request('/api/proposals/analyze', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  companyProposals: (companyId) => request(
    `/api/proposals/company/${encodeURIComponent(companyId)}`,
  ),
  getProposalAnalysis: (analysisId) => request(`/api/proposals/${encodeURIComponent(analysisId)}`),
};
