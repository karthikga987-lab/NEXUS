import { useState } from 'react';
import { Activity, AlertTriangle, BrainCircuit, Building2, CalendarDays, CheckCircle2, ChevronDown, ChevronUp, Database, ExternalLink, FileClock, FileText, Globe2, LoaderCircle, MessageSquare, Network, Quote, ShieldCheck, Sparkles, Workflow } from 'lucide-react';
import { api } from '../api/client';

function displayValue(value) {
  if (value === null || value === undefined || value === '') {
    return 'Not specified';
  }

  if (typeof value === 'string') return value;

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value.map(displayValue).join(', ');
  }

  return JSON.stringify(value, null, 2);
}

function EvidenceCard({ item, external = false }) {
  return (
    <article className="evidence-card">
      <div className="evidence-card-top">
        <span className={`evidence-label ${external ? 'external' : 'internal'}`}>
          {external ? 'EXTERNAL · PUBLIC' : item.evidence_scope === 'authorized_internal' ? 'AUTHORIZED INTERNAL' : 'PUBLIC COMPANY SOURCE'}
        </span>
        <span className="evidence-confidence">
          Similarity: {typeof item.similarity === 'number'
            ? `${(item.similarity * 100).toFixed(1)}%`
            : 'Not available'}
        </span>
      </div>

      <h4>{item.source_title || 'Untitled source'}</h4>

      <p className="evidence-company">
        {item.source_company_name || (external ? 'External company' : 'Your company')}
        {item.source_company_industry
          ? ` · ${item.source_company_industry}`
          : ''}
      </p>

      <blockquote className="evidence-passage">
        {item.retrieved_passage || 'No passage returned.'}
      </blockquote>

      <div className="evidence-card-bottom">
        <span>{item.permission_status || 'Permission not specified'}</span>
        {item.source_url && (
          <a href={item.source_url} target="_blank" rel="noreferrer">
            Open source <ExternalLink size={13} />
          </a>
        )}
      </div>
    </article>
  );
}

function ClaimCard({ claim }) {
  const scope = claim.evidence_scope || 'unknown';

  return (
    <article className="claim-card">
      <div className="claim-heading">
        <span className={`scope-tag ${scope}`}>
          {scope.toUpperCase()}
        </span>
        <span className="claim-status">
          {claim.evidence_status || 'Cited context'}
        </span>
      </div>

      <p>{claim.statement || 'Claim text unavailable.'}</p>

      {claim.sources?.length > 0 && (
        <div className="claim-sources">
          {claim.sources.map((source) => (
            <div key={source.source_id} className="claim-source">
              <span>{source.source_company_name || 'Source'}:</span>
              {source.source_title || source.source_id}
              {source.source_url && (
                <a href={source.source_url} target="_blank" rel="noreferrer">
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      {claim.source_ids?.length > 0 && !claim.sources?.length && (
        <small>{claim.source_ids.length} linked source(s)</small>
      )}
    </article>
  );
}

function formatDate(value) {
  if (!value) return 'Unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unavailable';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date);
}

function classificationName(value) {
  const labels = {
    documented: 'Documented fact',
    supported: 'Supported relationship',
    correlation: 'Correlation',
    inference: 'Inference',
    unknown: 'Unknown',
  };
  return labels[value] || 'Unknown';
}

function uniqueFeedback(feedbackData) {
  const records = new Map();
  (feedbackData?.trends || []).forEach((trend) => {
    (trend.evidence || []).forEach((item) => {
      const key = item.feedback_id || `${trend.topic}-${item.feedback_text}`;
      if (!records.has(key)) records.set(key, { ...item, topic: trend.topic });
    });
  });
  return [...records.values()];
}

function FeedbackForm({ companyId, onSubmit }) {
  const [text, setText] = useState('');
  const [productName, setProductName] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [rating, setRating] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function submit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setMessage('');
    try {
      await onSubmit({
        company_id: companyId,
        text: text.trim(),
        product_name: productName.trim() || null,
        source_url: sourceUrl.trim() || null,
        rating: rating === '' ? null : Number(rating),
      });
      setText('');
      setProductName('');
      setSourceUrl('');
      setRating('');
      setMessage('Feedback saved and analyzed.');
    } catch (err) {
      setMessage(`Feedback was not saved: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="feedback-submit-form" onSubmit={submit}>
      <h4>Add customer feedback</h4>
      <label>
        Feedback text
        <textarea value={text} onChange={(e) => setText(e.target.value)} required maxLength={10000} rows={3} />
      </label>
      <div className="feedback-submit-fields">
        <label>
          Product (optional)
          <input value={productName} onChange={(e) => setProductName(e.target.value)} maxLength={255} />
        </label>
        <label>
          Rating (optional)
          <input type="number" min="0" max="5" step="0.5" value={rating} onChange={(e) => setRating(e.target.value)} />
        </label>
      </div>
      <label>
        Feedback source URL (optional)
        <input type="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
      </label>
      <button className="secondary-action" type="submit" disabled={busy || !text.trim()}>
        {busy ? 'Saving feedback…' : 'Save feedback'}
      </button>
      {message && <p className="action-message" role="status">{message}</p>}
      <small>Feedback is user supplied. Topic and sentiment labels are heuristic, not documentary proof.</small>
    </form>
  );
}

export function RAGPanel({ companyId, companyName }) {
  const [query, setQuery] = useState('');
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [includeInternal, setIncludeInternal] = useState(false);

  async function ask(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError('');
    setAnswer(null);
    try {
      setAnswer(await api.answerQuestion({
        company_id: companyId,
        query: query.trim(),
        limit: 5,
        include_external_public: false,
        include_authorized_internal: includeInternal,
      }));
    } catch (err) {
      setError(err.message || 'Could not answer this question.');
    } finally {
      setBusy(false);
    }
  }

  if (!companyId) return null;
  return (
    <details className="rag-panel">
      <summary><BrainCircuit size={17} /> Ask NEXUS about {companyName}</summary>
      <form onSubmit={ask}>
        <label htmlFor="company-question">Ask a question about documented company history</label>
        <div className="rag-question-row">
          <input id="company-question" value={query} onChange={(e) => setQuery(e.target.value)} minLength={3} maxLength={2000} placeholder="What product changes are documented, and why?" />
          <button className="secondary-action" type="submit" disabled={busy || query.trim().length < 3}>
            {busy ? 'Checking evidence…' : 'Ask'}
          </button>
        </div>
        <label className="inline-check rag-internal-toggle">
          <input type="checkbox" checked={includeInternal} onChange={(e) => setIncludeInternal(e.target.checked)} />
          Include authorized local documents
        </label>
        <small className="local-only-note">Available only when the backend local internal-source feature is enabled.</small>
      </form>
      {error && <p className="action-error" role="alert">{error}</p>}
      {answer && (
        <div className="rag-answer" aria-live="polite">
          <span className="status-tag">{(answer.answer_status || 'unknown').replaceAll('_', ' ')}</span>
          <p>{answer.answer || 'No answer was returned.'}</p>
          {answer.requested_aspects?.length > 0 && (
            <div className="rag-aspect-list">
              {answer.requested_aspects.map((item) => (
                <span key={item.aspect}>{item.aspect}: {String(item.status).replaceAll('_', ' ')}</span>
              ))}
            </div>
          )}
          {answer.verified_claims?.map((claim, index) => (
            <article className="rag-claim" key={`${claim.statement}-${index}`}>
              <blockquote>{claim.statement}</blockquote>
              {(claim.citations || []).map((citation, citationIndex) => (
                <div key={`${citation.source_id}-${citationIndex}`} className="rag-citation">
                  <small>{citation.supporting_quote || claim.statement}</small>
                  {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">
                    {citation.source_title || citation.source_url}
                  </a>}
                </div>
              ))}
            </article>
          ))}
          {answer.unsupported_claims?.length > 0 && <p className="unavailable-note">Some generated claims did not pass evidence verification and are excluded from the answer.</p>}
        </div>
      )}
    </details>
  );
}

export default function CompanyIntelligence({
  company,
  data,
  loading,
  expanded,
  onToggle,
  onResearch,
  onProcess,
  actionBusy,
  actionMessage,
  onSubmitFeedback,
  onOpenProposals,
  onImportInternal,
  onProcessInternal,
  includeInternalInViews,
  onToggleInternalInViews,
}) {
  const events = data.events;
  const sources = data.sources;
  const verifiedEvents = (events || []).filter((event) =>
    ['documented', 'supported'].includes(event.evidence_classification)
  );
  const sourceById = new Map((sources || []).map((source) => [source.id, source]));
  const feedbackRecords = uniqueFeedback(data.feedback);
  const processingCounts = data.ingestion?.processing_status_counts || {};
  const processedCount = processingCounts.processed ?? processingCounts.completed ?? 0;
  const failedCount = processingCounts.failed ?? 0;
  const pendingCount = (processingCounts.pending ?? 0) + (processingCounts.collected ?? 0);
  const skippedCount = processingCounts.skipped ?? 0;
  const hasProcessingCounts = data.ingestion?.processing_status_counts;
  const graph = data.graph;
  const graphNodes = graph?.nodes || [];
  const graphEdges = graph?.edges || [];
  const graphLabels = new Map(graphNodes.map((node) => [
    node.id,
    node.title || node.name || node.product_name || node.source_id || node.id,
  ]));
  const topicCounts = (data.feedback?.trends || []).slice(0, 4);
  const collectedSources = (sources || []).filter((source) => source.content_kind !== 'search_snippet');
  const knowledgeItems = data.knowledgeItems || [];
  const proposals = data.proposals;
  const completedProposalAnalyses = (proposals || []).reduce(
    (total, proposal) => total + (proposal.analyses || []).filter(
      (analysis) => analysis.accessible && analysis.status === 'completed',
    ).length,
    0,
  );
  const [isSynthetic, setIsSynthetic] = useState(false);

  return (
    <section className="company-intelligence" aria-labelledby="company-overview-title">
      <div className="company-overview-heading">
        <div>
          <span className="eyebrow">COMPANY INTELLIGENCE</span>
          <h2 id="company-overview-title">{company.name}</h2>
          {company.website ? (
            <a className="company-website" href={company.website} target="_blank" rel="noreferrer">
              <Globe2 size={14} /> {company.website} <ExternalLink size={12} />
            </a>
          ) : (
            <span className="company-website unavailable">Website unavailable</span>
          )}
        </div>
        <span className="profile-source-label">Saved company data</span>
      </div>

      <div className="company-summary-grid">
        <article className="company-summary-card company-summary-main">
          <span className="summary-label">Company summary</span>
          <p className="company-description">
            {company.description?.trim()
              || 'No company summary is available in the saved profile.'}
          </p>
          <small>Summary text is taken from the company profile. NEXUS does not generate missing company facts here.</small>
        </article>

        <article className="company-summary-card">
          <span className="summary-label">Sources collected</span>
          <strong className="summary-number">{sources ? collectedSources.length : '—'}</strong>
          <small>{sources ? 'Full documents collected; search snippets excluded' : 'Source count unavailable'}</small>
        </article>

        <article className="company-summary-card">
          <span className="summary-label">Verified product events</span>
          <strong className="summary-number">{events ? verifiedEvents.length : '—'}</strong>
          <small>{events ? 'Documented or supported' : 'Event count unavailable'}</small>
        </article>

        <article className="company-summary-card">
          <span className="summary-label">Customer feedback</span>
          <strong className="summary-number">
            {data.feedback ? data.feedback.total_feedback ?? 0 : '—'}
          </strong>
          <small>{data.feedback ? 'Available feedback records' : 'Feedback count unavailable'}</small>
        </article>

        <article className="company-summary-card">
          <span className="summary-label">Saved proposals</span>
          <strong className="summary-number">{proposals ? proposals.length : '—'}</strong>
          <small>{proposals ? `${completedProposalAnalyses} available completed analysis(es)` : 'Proposal history unavailable'}</small>
        </article>

        <article className="company-summary-card company-processing-card">
          <span className="summary-label">Processing status</span>
          {loading && !data.ingestion ? (
            <span className="processing-state"><LoaderCircle size={15} className="spin" /> Loading status</span>
          ) : hasProcessingCounts ? (
            <div className="processing-counts">
              <span>{processedCount} processed</span>
              <span>{failedCount} failed</span>
              <span>{pendingCount} pending</span>
            </div>
          ) : (
            <span className="processing-state">Status unavailable</span>
          )}
        </article>
      </div>

      <div className="company-insights-row">
        <section className="company-insights-block">
          <div className="detail-section-title">
            <CheckCircle2 size={17} />
            <h3>Key documented insights</h3>
          </div>
          {loading && events === null ? (
            <p className="muted">Loading verified events…</p>
          ) : events === null ? (
            <p className="muted">Verified insights are unavailable because the events API could not be reached.</p>
          ) : verifiedEvents.length ? (
            <ul className="insight-list">
              {verifiedEvents.slice(0, 3).map((event) => (
                <li key={event.id}>
                  <span className={`classification-tag ${event.evidence_classification}`}>
                    {classificationName(event.evidence_classification)}
                  </span>
                  <strong>{event.title}</strong>
                  {event.event_date && <small>{formatDate(event.event_date)}</small>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="no-events-message">
              No verified historical product events have been identified in the available sources.
            </p>
          )}
        </section>

        <section className="company-insights-block">
          <div className="detail-section-title">
            <MessageSquare size={17} />
            <h3>Customer feedback themes</h3>
          </div>
          {data.feedback ? (
            topicCounts.length ? (
              <div className="feedback-topic-list">
                {topicCounts.map((topic) => (
                  <span key={topic.topic}>
                    {topic.topic}<b>{topic.total_feedback}</b>
                  </span>
                ))}
                <small>Topic and sentiment labels are heuristic summaries of submitted feedback.</small>
              </div>
            ) : (
              <p className="muted">No customer feedback topics are available.</p>
            )
          ) : (
            <p className="muted">Customer feedback data is unavailable from the current API.</p>
          )}
        </section>

        <section className="company-insights-block recent-proposals-block">
          <div className="detail-section-title">
            <FileClock size={17} />
            <h3>Recent proposal activity</h3>
          </div>
          {loading && proposals === null ? (
            <p className="muted">Loading saved proposal history…</p>
          ) : proposals === null ? (
            <p className="muted">Proposal history is unavailable; this does not mean there are no proposals.</p>
          ) : proposals.length ? (
            <>
              <ul className="recent-proposal-list">
                {proposals.slice(0, 3).map((proposal) => (
                  <li key={proposal.id}>
                    <strong>{proposal.title}</strong>
                    <small>{proposal.workflow_status === 'completed'
                      ? 'Analysis completed'
                      : proposal.workflow_status === 'submitted' && proposal.analyses?.some((item) => !item.accessible)
                        ? 'Analysis details restricted'
                        : 'Submitted · analysis pending'}</small>
                  </li>
                ))}
              </ul>
              <button className="recent-proposals-link" type="button" onClick={onOpenProposals}>Open proposal history</button>
            </>
          ) : (
            <p className="muted">No proposals have been submitted for this company.</p>
          )}
        </section>
      </div>

      <div className="company-summary-footnote">
        <span><strong>Product categories:</strong> {verifiedEvents.length
          ? 'Category labels are not provided by the current company API.'
          : 'Unavailable in the current company data.'}</span>
        <span><strong>Interpretation:</strong> Only documented or supported events count as verified; source collection alone is not evidence of a product event.</span>
      </div>

      <div className="company-action-row">
        <button className="secondary-action" type="button" onClick={onResearch} disabled={actionBusy || !company.website}>
          {actionBusy === 'research' ? 'Researching sources…' : 'Research public sources'}
        </button>
        <button className="secondary-action" type="button" onClick={onProcess} disabled={actionBusy || !sources?.length}>
          {actionBusy === 'process' ? 'Processing documents…' : 'Process public documents'}
        </button>
        {!company.website && <small>Add a company website to enable research.</small>}
      </div>
      <div className="internal-source-controls">
        <div>
          <strong>Authorized internal knowledge</strong>
          <p>Local trusted-development feature; no authentication is configured, so it must not be exposed as a production endpoint.</p>
        </div>
        <label className="file-import-label">
          Import .txt or .md
          <input type="file" accept=".txt,.md,text/plain,text/markdown" onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onImportInternal(file, isSynthetic);
            event.target.value = '';
          }} />
        </label>
        <label className="inline-check">
          <input type="checkbox" checked={isSynthetic} onChange={(event) => setIsSynthetic(event.target.checked)} />
          Label this file as synthetic demo data
        </label>
        <button className="secondary-action" type="button" onClick={onProcessInternal} disabled={actionBusy || !data.internalSources?.length}>
          {actionBusy === 'internal-process' ? 'Processing local documents…' : 'Process authorized local documents'}
        </button>
        <small>{data.internalSources?.length ?? 0} local document(s) · {data.internalSourcesError || (data.internalSources !== null ? 'Trusted-local access is enabled for this loopback request.' : 'Local internal access status unavailable until enabled.')}</small>
      </div>
      {actionMessage && <p className="action-message" role="status">{actionMessage}</p>}

      {data.internalSources?.length > 0 && expanded && (
        <div className="internal-source-list">
          <h3>Authorized local documents</h3>
          {data.internalSources.map((source) => (
            <article key={source.id}>
              <strong>{source.title}</strong>
              <span>{source.processing_status} · {source.evidence_origin}{source.is_synthetic ? ' · SYNTHETIC DEMO' : ''}</span>
            </article>
          ))}
        </div>
      )}

      <button
        className="details-toggle"
        type="button"
        aria-expanded={expanded}
        aria-controls="company-extracted-details"
        onClick={onToggle}
      >
        {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        {expanded ? 'Show summary' : 'View all extracted data'}
      </button>

      {expanded && (
        <div className="extracted-details" id="company-extracted-details">
          <section className="detail-section">
            <div className="detail-section-heading">
              <div className="detail-section-title"><FileText size={18} /><h3>Source documents</h3></div>
              <span className="count">{sources ? `${collectedSources.length} full · ${sources.length - collectedSources.length} snippet(s)` : 'Unavailable'}</span>
            </div>
            {sources?.length ? (
              <div className="source-detail-list">
                {sources.map((source) => (
                  <article className="source-detail-card" key={source.id}>
                    <div className="source-detail-heading">
                      <div>
                        <h4>{source.title || 'Untitled source'}</h4>
                        <span>{source.publisher || 'Publisher unavailable'}</span>
                      </div>
                      <span className={`status-tag ${source.processing_status || 'unknown'}`}>
                        {source.processing_status || 'Status unavailable'}
                      </span>
                    </div>
                    <div className="source-metadata-grid">
                      <span><b>Source type</b>{source.source_type || 'Unavailable'}</span>
                      <span><b>Publication date</b>{formatDate(source.publication_date)}</span>
                      <span><b>Event date</b>{formatDate(source.event_date)}</span>
                    </div>
                    {source.url && (
                      <a className="source-url" href={source.original_url || source.url} target="_blank" rel="noreferrer">
                        {source.original_url || source.url}<ExternalLink size={13} />
                      </a>
                    )}
                    <div className="source-provenance-line">
                      <span>{source.evidence_origin || 'Origin unavailable'}</span>
                      <span>{source.permission_status || 'Permission unavailable'}</span>
                      <span>Collected {formatDate(source.collected_at)}</span>
                    </div>
                    {source.content_excerpt && <blockquote className="source-excerpt">{source.content_excerpt}</blockquote>}
                    {source.extracted_event_evidence?.map((evidence) => (
                      <div className="event-evidence-quote" key={evidence.event_id}>
                        <strong>{evidence.event_title || 'Extracted event evidence'}</strong>
                        <blockquote className="source-excerpt">{evidence.evidence_quote || 'Supporting quote unavailable.'}</blockquote>
                        <small>{classificationName(evidence.evidence_classification)} · Extraction confidence {evidence.extraction_confidence == null ? 'unavailable' : `${Math.round(evidence.extraction_confidence * 100)}%`}</small>
                      </div>
                    ))}
                    {source.content_kind === 'search_snippet' && <small className="unavailable-note">Search snippet only. This is a discovery lead and is excluded from ingestion and evidence answers.</small>}
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">{sources === null ? 'Source data could not be loaded.' : 'No source documents are available.'}</p>
            )}
          </section>

          <section className="detail-section">
            <div className="detail-section-heading">
              <div className="detail-section-title"><CalendarDays size={18} /><h3>Extracted product events</h3></div>
              <span className="count">{events ? `${events.length} events` : 'Unavailable'}</span>
            </div>
            {events?.length ? (
              <div className="event-timeline">
                {events.map((event) => (
                  <article className="event-detail-card" key={event.id}>
                    <div className="event-detail-topline">
                      <span className={`classification-tag ${event.evidence_classification || 'unknown'}`}>
                        {classificationName(event.evidence_classification)}
                      </span>
                      <span className="event-type-tag">{event.event_type || 'Type unavailable'}</span>
                      <span className="event-date-label">{formatDate(event.event_date)}</span>
                    </div>
                    <h4>{event.title || 'Event title unavailable'}</h4>
                    <div className="event-metadata-line">
                      <span><b>Product</b> {event.product_name || 'Unavailable'}</span>
                      <span><b>Evidence class</b> {classificationName(event.evidence_classification)}</span>
                    </div>
                    <p>{event.description || 'Description unavailable.'}</p>
                    <div className="event-optional-fields">
                      <div><b>Stated reason</b><span>{event.stated_reason || 'Not documented'}</span></div>
                      <div><b>Reported outcome</b><span>{event.reported_outcome || 'Not documented'}</span></div>
                    </div>
                    <div className="event-provenance">
                      <strong><Quote size={14} /> Supporting source links</strong>
                      {event.source_ids?.length ? (
                        event.source_ids.map((sourceId) => {
                          const source = sourceById.get(sourceId);
                          return source ? (
                            <a key={sourceId} href={source.original_url || source.url} target="_blank" rel="noreferrer">
                              {source.title || source.original_url || source.url} <ExternalLink size={12} />
                            </a>
                          ) : (
                            <span key={sourceId}>Source {sourceId} — metadata unavailable</span>
                          );
                        })
                      ) : (
                        <span>No linked source is available from the events API.</span>
                      )}
                      {event.source_ids?.map((sourceId) => {
                        const source = sourceById.get(sourceId);
                        const evidence = source?.extracted_event_evidence?.find((item) => item.event_id === event.id);
                        return evidence ? (
                          <div className="event-evidence-quote" key={`${sourceId}-${event.id}`}>
                            <blockquote className="source-excerpt">{evidence.evidence_quote || 'Supporting quote unavailable.'}</blockquote>
                            <small>{source.publisher || 'Publisher unavailable'} · {source.original_url || source.url} · {classificationName(evidence.evidence_classification)} · Confidence {evidence.extraction_confidence == null ? 'unavailable' : `${Math.round(evidence.extraction_confidence * 100)}%`}</small>
                          </div>
                        ) : null;
                      })}
                      <small>Confidence is the model extraction estimate, not independent proof of truth.</small>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="no-events-message">
                {events === null
                  ? 'Event data could not be loaded.'
                  : 'No verified historical product events have been identified in the available sources.'}
              </p>
            )}
          </section>

          <section className="detail-section">
            <div className="detail-section-title"><ShieldCheck size={18} /><h3>Evidence and provenance</h3></div>
            {verifiedEvents.length ? (
              <div className="provenance-list">
                {verifiedEvents.map((event) => (
                  <article key={event.id}>
                    <div>
                      <strong>{event.title}</strong>
                      <span className={`classification-tag ${event.evidence_classification}`}>
                        {classificationName(event.evidence_classification)}
                      </span>
                    </div>
                    <p>{event.description || 'Event description unavailable.'}</p>
                    {(event.source_ids || []).map((sourceId) => {
                      const source = sourceById.get(sourceId);
                      return (
                        <span className="provenance-source" key={sourceId}>
                          {source?.publisher || 'Publisher unavailable'} · {formatDate(source?.publication_date)} · {source?.url || `Source ${sourceId}`}
                        </span>
                      );
                    })}
                    <small>Supporting excerpt, collection timestamp, permission status, and confidence are unavailable from the current API.</small>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">No documented or supported event claims are available to trace.</p>
            )}
          </section>

          <section className="detail-section">
            <div className="detail-section-title"><Activity size={18} /><h3>Research and processing</h3></div>
            {data.ingestion ? (
              <div className="research-status-grid">
                <span><b>Documents collected</b>{data.ingestion.total_sources ?? sources?.length ?? 'Unavailable'}</span>
                <span><b>Documents processed</b>{processedCount}</span>
                <span><b>Failed documents</b>{failedCount}</span>
                <span><b>Skipped documents</b>{skippedCount}</span>
              </div>
            ) : (
              <p className="muted">Processing totals are unavailable.</p>
            )}
            {sources?.some((source) => source.processing_status === 'failed') && (
              <div className="failed-source-list">
                <strong>Failed documents</strong>
                {sources.filter((source) => source.processing_status === 'failed').map((source) => (
                  <p key={source.id}>{source.title || source.url} — failure details are not exposed by the source API.</p>
                ))}
              </div>
            )}
            {data.researchStats?.latest_run?.counts && (
              <div className="research-status-grid">
                <span><b>URLs discovered</b>{data.researchStats.latest_run.counts.discovered ?? 0}</span>
                <span><b>Full docs collected</b>{data.researchStats.latest_run.counts.collected ?? 0}</span>
                <span><b>Discovery snippets</b>{data.researchStats.latest_run.counts.snippets_saved ?? 0}</span>
                <span><b>Duplicate URLs skipped</b>{data.researchStats.latest_run.counts.skipped_duplicates ?? 0}</span>
                <span><b>Events extracted</b>{data.researchStats.latest_run.counts.ingestion_events_extracted ?? 0}</span>
                <span><b>Knowledge items created</b>{data.researchStats.latest_run.counts.ingestion_new_knowledge_items ?? 0}</span>
                <span><b>Embedding chunks generated</b>{data.researchStats.latest_run.counts.ingestion_embedding_chunks_created ?? 0}</span>
              </div>
            )}
            {data.researchStats?.latest_run?.failure_summary && <p className="unavailable-note">Research note: {data.researchStats.latest_run.failure_summary}</p>}
          </section>

          <section className="detail-section">
            <div className="detail-section-heading">
              <div className="detail-section-title"><Database size={18} /><h3>Extracted knowledge items</h3></div>
              <span className="count">{knowledgeItems.length} items</span>
            </div>
            <label className="inline-check">
              <input type="checkbox" checked={includeInternalInViews} onChange={(event) => onToggleInternalInViews(event.target.checked)} />
              Include authorized local documents
            </label>
            {knowledgeItems.length ? (
              <div className="knowledge-item-list">
                {knowledgeItems.map((item) => (
                  <article className="knowledge-item-card" key={item.id}>
                    <div className="event-detail-topline">
                      <span className={`classification-tag ${item.evidence_classification || 'unknown'}`}>{classificationName(item.evidence_classification)}</span>
                      <span className="event-type-tag">{item.item_type || 'Knowledge'}</span>
                      {item.is_synthetic && <span className="status-tag">SYNTHETIC DEMO</span>}
                    </div>
                    <h4>{item.title}</h4>
                    <p>{item.description}</p>
                    <blockquote className="source-excerpt">{item.evidence_quote}</blockquote>
                    <small>{item.evidence_origin || 'Origin unavailable'} · {item.permission_status || 'Permission unavailable'} · Confidence {item.extraction_confidence == null ? 'unavailable' : `${Math.round(item.extraction_confidence * 100)}%`}</small>
                    {item.source_url?.startsWith('http') && <a className="source-url" href={item.source_url} target="_blank" rel="noreferrer">{item.source_title || item.source_url}<ExternalLink size={12} /></a>}
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">{data.knowledgeItems === null ? 'Knowledge items could not be loaded. Authorized internal retrieval requires local development access.' : 'No source-backed knowledge items are available yet.'}</p>
            )}
          </section>

          <section className="detail-section">
            <div className="detail-section-title"><MessageSquare size={18} /><h3>Customer feedback</h3></div>
            {data.feedback ? (
              <>
                <p className="feedback-caveat">Sentiment and topic labels are heuristic. Feedback describes customer reports and is not documentary proof of product events or outcomes.</p>
                {feedbackRecords.length ? (
                  <div className="feedback-record-list">
                    {feedbackRecords.map((record, index) => (
                      <article key={record.feedback_id || index}>
                        <div className="feedback-record-meta">
                          <span>{record.topic || 'general'}</span>
                          <span>{record.sentiment || 'unknown'} sentiment</span>
                          {record.rating != null && <span>Rating {record.rating}</span>}
                        </div>
                        <p>{record.feedback_text || 'Feedback text unavailable.'}</p>
                        {record.source_url && <a href={record.source_url} target="_blank" rel="noreferrer">Feedback source <ExternalLink size={12} /></a>}
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="muted">No feedback records are available.</p>
                )}
              </>
            ) : (
              <p className="muted">Feedback details are unavailable from the current API.</p>
            )}
            <FeedbackForm companyId={company.id} onSubmit={onSubmitFeedback} />
          </section>

          <section className="detail-section">
            <div className="detail-section-heading">
              <div className="detail-section-title"><Network size={18} /><h3>Knowledge graph</h3></div>
              {graph && <span className="count">{graph.summary?.node_count ?? graphNodes.length} nodes · {graph.summary?.edge_count ?? graphEdges.length} links</span>}
            </div>
            {graph ? (
              graphEdges.length ? (
                <div className="graph-connection-list">
                  {graphEdges.map((edge) => (
                    <article key={edge.id}>
                      <span>{graphLabels.get(edge.source) || edge.source}</span>
                      <b>{edge.relation_type || edge.relationship_type || 'connected to'}</b>
                      <span>{graphLabels.get(edge.target) || edge.target}</span>
                      <small>{classificationName(edge.evidence_classification || edge.evidence_status)}</small>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted">The knowledge graph has no persisted relationships for this company yet.</p>
              )
            ) : (
              <p className="muted">Knowledge graph data is unavailable.</p>
            )}
          </section>

          <details className="technical-details">
            <summary><Workflow size={16} /> Advanced processing details</summary>
            <p>Semantic embeddings support retrieval, but the current UI API does not expose vector values or individual chunk records. They are not shown here.</p>
            {data.errors?.length > 0 && (
              <ul>{data.errors.map((error) => <li key={error}>{error}</li>)}</ul>
            )}
          </details>
        </div>
      )}
    </section>
  );
}
