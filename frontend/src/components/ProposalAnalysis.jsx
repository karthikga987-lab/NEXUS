
import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileClock,
  Lightbulb,
  LoaderCircle,
  Network,
  Search,
  Sparkles,
  Users,
} from 'lucide-react';
import { api } from '../api/client';
import { runProposalWorkflow } from '../proposalWorkflow';
import { hasVerifiedProposalClaims } from '../proposalAssistant';
import './ProposalAnalysis.css';

function EvidenceCard({ item }) {
  const relevanceLabels = {
    directly_relevant: 'Directly relevant context',
    same_company_historical: 'Same-company historical context',
    competitor_context: 'Competitor context',
    general_industry_context: 'General industry context',
    related_insufficient: 'Related, but insufficient',
    irrelevant: 'Irrelevant',
  };

  return (
    <article className="proposal-evidence-card">
      <div className="proposal-card-top">
        <span className="proposal-category">
          {item.evidence_scope || item.permission_status || 'Evidence scope unavailable'}
        </span>
        <span>
          {item.similarity == null
            ? 'Similarity unavailable'
            : `${(Number(item.similarity) * 100).toFixed(1)}% similarity`}
        </span>
      </div>
      <h4>{item.source_title || 'Untitled source'}</h4>
      <p>{item.source_company_name || 'Company unavailable'}</p>
      {(item.publisher || item.source_type || item.publication_date) && (
        <p className="proposal-source-metadata">
          {[item.publisher, item.source_type, item.publication_date]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
      <p className="proposal-relevance-label">
        Relevance assessment: {relevanceLabels[item.proposal_relevance] || 'Not classified; candidate only'}
        {item.proposal_aspect ? ` · ${item.proposal_aspect}` : ''}
      </p>
      {item.proposal_relevance_reason && (
        <p className="proposal-relevance-note">{item.proposal_relevance_reason}</p>
      )}
      <blockquote>{item.retrieved_passage || 'Retrieved excerpt unavailable.'}</blockquote>
      {item.source_url && (
        <a href={item.source_url} target="_blank" rel="noreferrer">
          Open source <ExternalLink size={13} />
        </a>
      )}
    </article>
  );
}

function formatDate(value) {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Date unavailable'
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(date);
}

function workflowLabel(proposal) {
  if (proposal.workflow_status === 'completed') return 'Analysis completed';
  if (proposal.analyses?.some((item) => !item.accessible)) return 'Analysis details restricted';
  if (proposal.analyses?.length) return proposal.analyses[0].status || 'Analysis submitted';
  return 'Submitted · analysis pending';
}

function KnowledgeContext({ context }) {
  const events = Array.isArray(context?.events) ? context.events : [];

  return (
    <section className="proposal-analysis-section">
      <h3><Network size={17} /> Company knowledge context</h3>

      <p>
        {context?.event_count ?? events.length} historical event(s) were available
        in the company knowledge graph for this analysis.
      </p>

      {context?.interpretation_warning && (
        <small>{context.interpretation_warning}</small>
      )}

      {events.length ? (
        <div className="proposal-evidence-grid">
          {events.map((event, index) => (
            <article
              className="proposal-evidence-card"
              key={event.event_id || `${event.title || 'event'}-${index}`}
            >
              <div className="proposal-card-top">
                <span className="proposal-category">
                  {event.event_type || 'Historical event'}
                </span>
                <span>{event.evidence_classification || 'Classification unavailable'}</span>
              </div>

              <h4>{event.title || event.product_name || 'Untitled historical event'}</h4>

              {event.product_name && <p>Product: {event.product_name}</p>}
              {event.event_date && <p>Event date: {formatDate(event.event_date)}</p>}
              {event.description && <p>{event.description}</p>}
              {event.stated_reason && (
                <p><strong>Documented reason:</strong> {event.stated_reason}</p>
              )}
              {event.reported_outcome && (
                <p><strong>Reported outcome:</strong> {event.reported_outcome}</p>
              )}
              {event.extraction_confidence != null && (
                <p>
                  <strong>Extraction confidence:</strong>{' '}
                  {(Number(event.extraction_confidence) * 100).toFixed(1)}%
                </p>
              )}

              {Array.isArray(event.relationships) && event.relationships.length > 0 && (
                <div>
                  <strong>Recorded relationships</strong>
                  <ul>
                    {event.relationships.map((relationship, relationshipIndex) => (
                      <li key={relationship.id || relationshipIndex}>
                        {relationship.relationship_type ||
                          relationship.relation_type ||
                          relationship.type ||
                          'Relationship type unavailable'}
                        {relationship.evidence_classification
                          ? ` · ${relationship.evidence_classification}`
                          : ''}
                        {relationship.confidence != null
                          ? ` · ${(Number(relationship.confidence) * 100).toFixed(1)}% confidence`
                          : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {Array.isArray(event.source_ids) && event.source_ids.length > 0 && (
                <small>Supporting source IDs: {event.source_ids.join(', ')}</small>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p>
          No historical product events were returned by the company knowledge
          graph. This does not mean that no historical events occurred; they
          are simply unavailable in the current retrieved records.
        </p>
      )}
    </section>
  );
}

function CustomerFeedback({ context }) {
  const feedback = Array.isArray(context?.feedback) ? context.feedback : [];

  return (
    <section className="proposal-analysis-section">
      <h3><Users size={17} /> Customer feedback signal</h3>

      <p>
        {context?.feedback_count ?? feedback.length} proposal-relevant record(s)
        selected from {context?.total_company_feedback_available ?? 0} company
        feedback record(s).
      </p>

      {context?.interpretation_warning && (
        <small>{context.interpretation_warning}</small>
      )}

      {feedback.length ? (
        <div className="proposal-evidence-grid">
          {feedback.map((item, index) => (
            <article
              className="proposal-evidence-card"
              key={item.feedback_id || `${item.source_id || 'feedback'}-${index}`}
            >
              <div className="proposal-card-top">
                <span className="proposal-category">
                  {item.sentiment || 'Sentiment unavailable'}
                </span>
                <span>{item.feedback_type || 'Feedback type unavailable'}</span>
              </div>

              <blockquote>
                {item.feedback_text || 'Feedback text unavailable.'}
              </blockquote>

              {item.product_name && <p>Product: {item.product_name}</p>}
              {item.rating != null && <p>Rating: {item.rating}</p>}
              {item.feedback_date && (
                <p>Date: {formatDate(item.feedback_date)}</p>
              )}
              {Array.isArray(item.topics) && item.topics.length > 0 && (
                <p>Topics: {item.topics.join(', ')}</p>
              )}
              {item.source_url && (
                <a href={item.source_url} target="_blank" rel="noreferrer">
                  Open feedback source <ExternalLink size={13} />
                </a>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p>
          No proposal-relevant customer feedback records were returned for this
          analysis. The system will not invent customer opinions or feedback
          patterns.
        </p>
      )}
    </section>
  );
}

const WORKFLOW_STAGES = [
  ['proposal_save', 'Save proposal to this company'],
  ['research', 'Public company research'],
  ['ingestion', 'Document ingestion and embeddings'],
  ['knowledge_graph', 'Evidence-backed relationship update'],
  ['proposal_analysis', 'Proposal analysis and save'],
];

export default function ProposalAnalysis({ company, onRefreshData = () => {} }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [includeFreshResearch, setIncludeFreshResearch] = useState(false);
  const [includeInternal, setIncludeInternal] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [selectedProposal, setSelectedProposal] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const [historyReload, setHistoryReload] = useState(0);
  const [openingAnalysisId, setOpeningAnalysisId] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [workflowStages, setWorkflowStages] = useState(null);
  const [refreshReport, setRefreshReport] = useState(null);

  useEffect(() => {
    let active = true;
    setHistoryLoading(true);
    setHistoryError('');

    api.companyProposals(company.id)
      .then((items) => {
        if (active) setHistory(Array.isArray(items) ? items : []);
      })
      .catch((requestError) => {
        if (active) {
          setHistory([]);
          setHistoryError(requestError.message || 'Saved proposals could not be loaded.');
        }
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });

    return () => {
      active = false;
    };
  }, [company.id, historyReload]);

  const completedAnalysisCount = useMemo(
    () => history.reduce(
      (total, proposal) => total + (proposal.analyses || []).filter(
        (item) => item.accessible && item.status === 'completed',
      ).length,
      0,
    ),
    [history],
  );

  async function submit(event) {
    event.preventDefault();
    setError('');
    setAnalysis(null);
    setSelectedProposal(null);
    setWorkflowStages(Object.fromEntries(
      WORKFLOW_STAGES.map(([key]) => [key, { status: 'pending', detail: '' }]),
    ));
    setRefreshReport(null);
    setBusy(true);

    try {
      const result = await runProposalWorkflow({
        api,
        company,
        proposal: { title, description },
        includeFreshResearch,
        includeInternal,
        onStages: setWorkflowStages,
        onRefreshData,
        onProposalSaved: (savedProposal) => {
          setSelectedProposal(savedProposal);
          setHistoryReload((value) => value + 1);
        },
      });

      setSelectedProposal(result.proposal);
      setAnalysis(result.analysis);
      setRefreshReport(result.refresh);
      setHistoryReload((value) => value + 1);
    } catch (requestError) {
      setError(requestError.message || 'Proposal analysis failed.');
      setHistoryReload((value) => value + 1);
    } finally {
      setBusy(false);
    }
  }

  async function openProposal(proposal, analysisItem = null) {
    setSelectedProposal(proposal);
    setError('');
    setAnalysis(null);

    if (!analysisItem) return;

    if (!analysisItem.accessible) {
      setAnalysis(null);
      setError(
        'This saved analysis uses restricted source material and is unavailable through the public analysis endpoint.',
      );
      return;
    }

    setOpeningAnalysisId(analysisItem.id);

    try {
      const savedAnalysis = await api.getProposalAnalysis(analysisItem.id);
      setAnalysis(savedAnalysis);
      setSelectedProposal(savedAnalysis.proposal || proposal);
    } catch (requestError) {
      setError(requestError.message || 'The saved analysis could not be reopened.');
    } finally {
      setOpeningAnalysisId('');
    }
  }

  const evidence = analysis?.evidence || [
    ...(analysis?.internal_evidence || []),
    ...(analysis?.external_evidence || []),
  ];

  const sourceById = new Map(evidence.map((item) => [item.source_id, item]));
  const feedbackCount = analysis?.customer_feedback_context?.feedback_count;
  const currentProposal = analysis?.proposal || selectedProposal;
  const draftEdited = Boolean(title.trim() || description.trim());
  const isReopened = Boolean(analysis?.proposal);

  return (
    <div className="proposal-page">
      <header className="proposal-heading">
        <div>
          <span className="proposal-eyebrow">PROPOSAL EVALUATION</span>
          <h2>Evidence-backed analysis</h2>
          <p>
            Submitted ideas and completed analyses are saved to this company
            workspace and can be reopened below.
          </p>
        </div>
        <span className="proposal-demo-label">
          <span className="score-status">{analysis?.status || 'History available'}</span>
        </span>
      </header>

      <section className="proposal-summary" aria-label="Proposal history summary">
        <article className="proposal-summary-card">
          <div className="proposal-summary-top"><span>Saved proposals</span><FileClock size={15} /></div>
          <h2>{historyLoading ? '…' : historyError ? '—' : history.length}</h2>
          <p>{historyError ? 'History unavailable' : 'For this company'}</p>
        </article>
        <article className="proposal-summary-card">
          <div className="proposal-summary-top"><span>Completed analyses</span><CheckCircle2 size={15} /></div>
          <h2>{historyLoading ? '…' : historyError ? '—' : completedAnalysisCount}</h2>
          <p>Saved, accessible results</p>
        </article>
        <article className="proposal-summary-card">
          <div className="proposal-summary-top"><span>Evidence passages</span><Search size={15} /></div>
          <h2>{analysis ? evidence.length : '—'}</h2>
          <p>Returned for the selected analysis</p>
        </article>
        <article className="proposal-summary-card">
          <div className="proposal-summary-top"><span>Evidence-checked claims</span><CheckCircle2 size={15} /></div>
          <h2>{analysis ? (analysis.claims?.length ?? 0) : '—'}</h2>
          <p>Claims in the selected result</p>
        </article>
        <article className="proposal-summary-card">
          <div className="proposal-summary-top"><span>Relevant feedback</span><Lightbulb size={15} /></div>
          <h2>{feedbackCount ?? (analysis ? 0 : '—')}</h2>
          <p>Company feedback selected by API</p>
        </article>
      </section>

      <section className="proposal-history" aria-labelledby="proposal-history-title">
        <div className="proposal-history-heading">
          <div>
            <h3 id="proposal-history-title">Saved proposal history</h3>
            <p>
              Proposals are user-submitted ideas, not documented company
              decisions or product events.
            </p>
          </div>
          <Clock3 size={18} />
        </div>

        {historyLoading ? (
          <p className="proposal-history-state" role="status">
            <LoaderCircle className="spin" size={16} /> Loading saved proposals…
          </p>
        ) : historyError ? (
          <p className="proposal-history-state error" role="alert">{historyError}</p>
        ) : history.length === 0 ? (
          <p className="proposal-history-state">
            No submitted proposals are saved for {company.name} yet.
          </p>
        ) : (
          <div className="proposal-list">
            {history.map((proposal) => (
              <article className="proposal-card" key={proposal.id}>
                <div className="proposal-card-top">
                  <span className="proposal-category">User-submitted proposal</span>
                  <span className={`proposal-status ${proposal.workflow_status === 'completed' ? 'analysed' : 'pending'}`}>
                    {workflowLabel(proposal)}
                  </span>
                </div>

                <div className="proposal-card-copy">
                  <h4>{proposal.title}</h4>
                  <p>{proposal.description}</p>
                </div>

                <div className="proposal-card-bottom">
                  <span>
                    Submitted {formatDate(proposal.created_at)} · Proposal ID {proposal.id}
                  </span>
                  <div className="proposal-history-actions">
                    {proposal.analyses?.length ? proposal.analyses.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        disabled={!item.accessible || openingAnalysisId === item.id}
                        onClick={() => openProposal(proposal, item)}
                      >
                        {openingAnalysisId === item.id
                          ? <LoaderCircle className="spin" size={13} />
                          : null}
                        {item.accessible
                          ? `Open analysis · ${formatDate(item.completed_at || item.created_at)}`
                          : 'Restricted analysis'}
                      </button>
                    )) : (
                      <button type="button" onClick={() => openProposal(proposal)}>
                        View submitted proposal
                      </button>
                    )}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {openingAnalysisId && (
        <p className="proposal-history-state" role="status">
          <LoaderCircle className="spin" size={16} /> Reopening saved analysis…
        </p>
      )}

      <section className="proposal-submit-panel">
        <div className="proposal-form-heading">
          <h2>Analyze a product proposal</h2>
          <Lightbulb size={20} />
        </div>
        <p>
          Analyze and Save first refreshes this company's bounded public
          research and document processing, then analyzes the proposal against
          persisted evidence. Existing records remain available during refresh.
        </p>

        <form className="proposal-form" onSubmit={submit}>
          <label htmlFor="proposal-title">Proposal title</label>
          <input
            id="proposal-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={500}
            required
          />

          <label htmlFor="proposal-description">Description (at least 20 characters)</label>
          <textarea
            id="proposal-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            minLength={20}
            maxLength={12000}
            rows={5}
            required
          />

          {draftEdited && !selectedProposal && (
            <small className="proposal-draft-note">
              Draft · not saved yet. Submit the proposal to retain it in company history.
            </small>
          )}

          <label className="inline-check">
            <input
              type="checkbox"
              checked={includeFreshResearch}
              onChange={(event) => setIncludeFreshResearch(event.target.checked)}
            />
            Run bounded fresh public competitor research
          </label>

          <label className="inline-check">
            <input
              type="checkbox"
              checked={includeInternal}
              onChange={(event) => setIncludeInternal(event.target.checked)}
            />
            Include authorized local documents
          </label>

          <small>
            Cached public evidence is the default. Local internal access is
            loopback-only development functionality; no authentication is configured.
          </small>

          <button
            className="proposal-add-button"
            type="submit"
            disabled={busy || description.trim().length < 20}
          >
            {busy
              ? <><LoaderCircle className="spin" size={16} /> Refreshing company intelligence…</>
              : <><Sparkles size={16} /> Analyze and save proposal</>}
          </button>
        </form>
      </section>

      {error && (
        <div className="error-panel" role="alert">
          <AlertTriangle size={17} />{error}
        </div>
      )}

      {busy && (
        <div className="proposal-workflow-progress" role="status" aria-live="polite">
          <h3><LoaderCircle className="spin" size={17} /> Refreshing {company.name} intelligence</h3>
          <ol>
            {WORKFLOW_STAGES.map(([key, label]) => {
              const item = workflowStages?.[key] || { status: 'pending' };
              return (
                <li key={key} className={`workflow-stage ${item.status}`}>
                  <span className="workflow-stage-indicator" aria-hidden="true" />
                  <span>{label}</span>
                  <strong>{item.status.replaceAll('_', ' ')}</strong>
                  {item.detail ? <small>{item.detail}</small> : null}
                </li>
              );
            })}
          </ol>
          <p>Source discovery, ingestion and relationship failures are reported as partial results; they do not replace persisted evidence.</p>
        </div>
      )}

      {refreshReport?.status === 'partial' && (
        <div className="proposal-refresh-warning" role="status">
          <strong>Analysis completed with a partial intelligence refresh.</strong>
          <p>The recommendation uses evidence already persisted for this company. Review refresh status before treating the collection as complete.</p>
          {refreshReport.errors?.length ? <ul>{refreshReport.errors.map((item) => <li key={item}>{item}</li>)}</ul> : null}
        </div>
      )}

      {currentProposal && (
        <section className="proposal-analysis-result" aria-live="polite">
          <div className="proposal-detail-heading">
            <div>
              <span className="proposal-status">
                {analysis?.status || currentProposal.status || 'submitted'}
              </span>
              <h2>{analysis ? 'Analysis result' : 'Submitted proposal'}</h2>
            </div>
            <span>{analysis?.analysis_id ? `Analysis ${analysis.analysis_id}` : ''}</span>
          </div>

          <article className="proposal-selected-submission">
            <span>User-submitted proposal · not a documented company decision</span>
            <h3>{currentProposal.title}</h3>
            <p>{currentProposal.description}</p>
          </article>

          {analysis ? (
            <>
              {isReopened && (
                <p className="proposal-persistence-note">
                  {analysis.evidence_snapshot_available
                    ? `Reopened with the evidence and public graph context captured at ${formatDate(analysis.snapshot_captured_at)}. Public source-linked feedback is shown where it was included in the snapshot.`
                    : 'Historical evidence snapshot unavailable. The recommendation, risks, limitations and source links may remain, while graph and feedback context below is refreshed from current public records.'}
                </p>
              )}

              {!hasVerifiedProposalClaims(analysis) && (
                <p className="proposal-verification-warning" role="note">
                  No factual claims in this analysis passed citation verification. Treat the recommendation and risks as AI-generated judgment, not verified company facts.
                </p>
              )}

              <article className="proposal-recommendation">
                <h3><Sparkles size={17} /> Recommendation</h3>
                <p>{analysis.recommendation || 'No recommendation was returned.'}</p>
              </article>

              <section className="proposal-analysis-section">
                <h3><AlertTriangle size={17} /> Risks</h3>
                {analysis.risks?.length ? (
                  <ul>
                    {analysis.risks.map((risk, index) => (
                      <li key={`${index}-${risk}`}>
                        {typeof risk === 'string' ? risk : JSON.stringify(risk)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No risks were returned by the API.</p>
                )}
              </section>

              <section className="proposal-analysis-section">
                <h3><CheckCircle2 size={17} /> Evidence-linked claims</h3>
                {analysis.claims?.some((claim) => claim.verification_status === 'verified') ? (
                  analysis.claims
                    .filter((claim) => claim.verification_status === 'verified')
                    .map((claim, index) => (
                    <article className="proposal-claim" key={`${claim.statement}-${index}`}>
                      <p>{claim.statement || 'Claim text unavailable.'}</p>
                      <span>
                        {claim.evidence_status || claim.evidence_classification || 'Evidence status unavailable'}
                      </span>
                      {(claim.sources || []).map((source) => (
                        <a
                          key={source.source_id}
                          href={source.source_url || undefined}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {source.source_title || source.source_id} <ExternalLink size={12} />
                        </a>
                      ))}
                      {(claim.source_ids || [])
                        .filter((id) => !claim.sources?.some((source) => source.source_id === id))
                        .map((id) => (
                          <span key={id}>
                            {sourceById.get(id)?.source_title || `Source ${id}`}
                          </span>
                        ))}
                    </article>
                  ))
                ) : (
                  <p>No factual claims passed evidence verification.</p>
                )}
              </section>

              {analysis.unverified_claims?.length > 0 && (
                <section className="proposal-analysis-section" aria-label="Claims not verified">
                  <h3><AlertTriangle size={17} /> Claims not verified</h3>
                  <p>These statements did not have a saved source excerpt that directly supported their complete wording.</p>
                  {analysis.unverified_claims.map((claim, index) => (
                    <article className="proposal-claim" key={`${claim.statement}-${index}`}>
                      <p>{claim.statement || 'Claim text unavailable.'}</p>
                      <span>{claim.evidence_status || 'Not verified'}</span>
                    </article>
                  ))}
                </section>
              )}

              <section className="proposal-analysis-section">
                <h3><Search size={17} /> Retrieved evidence and context</h3>
                {evidence.length ? (
                  <div className="proposal-evidence-grid">
                    {evidence.map((item, index) => (
                      <EvidenceCard
                        key={`${item.source_id}-${item.chunk_index ?? index}`}
                        item={item}
                      />
                    ))}
                  </div>
                ) : (
                  <p>
                    {isReopened
                      ? 'Per-run evidence passages were not persisted. Any verified source-linked claims are shown above.'
                      : 'No documentary evidence was returned. The recommendation should be treated conservatively.'}
                  </p>
                )}
                <small>
                  Relevance assessments are contextual model classifications,
                  not fact verification. External sources describe their named
                  company and do not establish the proposing company’s history.
                </small>
              </section>

              {analysis.company_knowledge_context && (
                <KnowledgeContext context={analysis.company_knowledge_context} />
              )}

              {analysis.customer_feedback_context && (
                <CustomerFeedback context={analysis.customer_feedback_context} />
              )}

              {analysis.external_research && (
                <section className="proposal-analysis-section">
                  <h3>External research</h3>
                  <p>
                    Status: {analysis.external_research.status || 'Unavailable'}
                    {' · '}
                    Evidence origin: {analysis.external_research.evidence_origin || 'Unavailable'}
                  </p>
                </section>
              )}

              <section className="proposal-analysis-section">
                <h3>Limitations</h3>
                {analysis.limitations?.length ? (
                  <ul>
                    {analysis.limitations.map((item, index) => (
                      <li key={`${index}-${item}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No limitations were returned.</p>
                )}
              </section>
            </>
          ) : (
            <div className="proposal-awaiting">
              <strong>
                {currentProposal.analyses?.length
                  ? 'A saved analysis exists for this proposal.'
                  : 'This proposal is submitted; no completed analysis is available.'}
              </strong>
              <p>
                {currentProposal.analyses?.length
                  ? 'The proposal remains saved. Reopen an accessible analysis from the history list above.'
                  : 'It remains saved in this company’s history. A failed or unfinished analysis does not erase the submission.'}
              </p>
            </div>
          )}
        </section>
      )}

      <p className="proposal-demo-notice">
        Proposal text represents a user-submitted hypothetical idea. It is not
        an actual product launch, historical event, company decision or customer feedback.
      </p>
    </div>
  );
}
