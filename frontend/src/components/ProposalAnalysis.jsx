import { useState } from 'react';
import { Search, Lightbulb, CheckCircle2, AlertTriangle, X, Sparkles, ExternalLink, LoaderCircle } from 'lucide-react';
import { api } from '../api/client';
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

  return <article className="proposal-evidence-card">
    <div className="proposal-card-top"><span className="proposal-category">{item.evidence_scope || item.permission_status || 'Evidence scope unavailable'}</span><span>{item.similarity == null ? 'Similarity unavailable' : `${(Number(item.similarity) * 100).toFixed(1)}% similarity`}</span></div>
    <h4>{item.source_title || 'Untitled source'}</h4>
    <p>{item.source_company_name || 'Company unavailable'}</p>
    <p className="proposal-relevance-label">
      Relevance assessment: {relevanceLabels[item.proposal_relevance] || 'Not classified; candidate only'}
      {item.proposal_aspect ? ` · ${item.proposal_aspect}` : ''}
    </p>
    {item.proposal_relevance_reason && <p className="proposal-relevance-note">{item.proposal_relevance_reason}</p>}
    <blockquote>{item.retrieved_passage || 'Retrieved excerpt unavailable.'}</blockquote>
    {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">Open source <ExternalLink size={13} /></a>}
  </article>;
}

export default function ProposalAnalysis({ company }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [includeFreshResearch, setIncludeFreshResearch] = useState(false);
  const [includeInternal, setIncludeInternal] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError('');
    setAnalysis(null);
    setBusy(true);
    try {
      const result = await api.analyzeProposal({
        company_id: company.id,
        title: title.trim(),
        description: description.trim(),
        include_fresh_external_research: includeFreshResearch,
        include_authorized_internal: includeInternal,
      });
      setAnalysis(result);
    } catch (requestError) {
      setError(requestError.message || 'Proposal analysis failed.');
    } finally {
      setBusy(false);
    }
  }

  const evidence = analysis?.evidence || [
    ...(analysis?.internal_evidence || []),
    ...(analysis?.external_evidence || []),
  ];
  const sourceById = new Map(evidence.map((item) => [item.source_id, item]));
  const feedbackCount = analysis?.customer_feedback_context?.feedback_count;

  return (
    <div className="proposal-page">
      <header className="proposal-heading"><div><span className="proposal-eyebrow">PROPOSAL EVALUATION</span><h2>Evidence-backed analysis</h2><p>Analyze a proposal against eligible company history and feedback returned by the backend.</p></div><span className="proposal-demo-label"><span className="score-status">{analysis?.status || "No analysis submitted"}</span></span></header>
      <section className="proposal-summary" aria-label="Current analysis summary">
        <article className="proposal-summary-card"><div className="proposal-summary-top"><span>Evidence passages</span><Search size={15} /></div><h2>{analysis ? evidence.length : "—"}</h2><p>Returned for this request</p></article>
        <article className="proposal-summary-card"><div className="proposal-summary-top"><span>Evidence-checked claims</span><CheckCircle2 size={15} /></div><h2>{analysis ? (analysis.claims?.length ?? 0) : "—"}</h2><p>Claims in current result</p></article>
        <article className="proposal-summary-card"><div className="proposal-summary-top"><span>Relevant feedback</span><Lightbulb size={15} /></div><h2>{feedbackCount ?? (analysis ? 0 : "—")}</h2><p>Company feedback selected by API</p></article>
      </section>
      <section className="proposal-submit-panel">
        <div className="proposal-form-heading"><h2>Analyze a product proposal</h2><Lightbulb size={20} /></div>
        <p>Analysis uses relevant saved evidence by default. Fresh external research is optional and may add time.</p>
        <form className="proposal-form" onSubmit={submit}>
          <label htmlFor="proposal-title">Proposal title</label>
          <input id="proposal-title" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={500} required />
          <label htmlFor="proposal-description">Description (at least 20 characters)</label>
          <textarea id="proposal-description" value={description} onChange={(event) => setDescription(event.target.value)} minLength={20} maxLength={12000} rows={5} required />
          <label className="inline-check"><input type="checkbox" checked={includeFreshResearch} onChange={(event) => setIncludeFreshResearch(event.target.checked)} /> Run bounded fresh public competitor research</label>
          <label className="inline-check"><input type="checkbox" checked={includeInternal} onChange={(event) => setIncludeInternal(event.target.checked)} /> Include authorized local documents</label>
          <small>Cached public evidence is the default. Local internal access is loopback-only development functionality; no authentication is configured.</small>
          <button className="proposal-add-button" type="submit" disabled={busy || description.trim().length < 20}>
            {busy ? <><LoaderCircle className="spin" size={16} /> Analyzing evidence…</> : <><Sparkles size={16} /> Analyze proposal</>}
          </button>
        </form>
      </section>

      {error && <div className="error-panel" role="alert"><AlertTriangle size={17} />{error}</div>}
      {busy && <div className="loading-panel" role="status"><LoaderCircle className="spin" size={20} />Retrieving evidence and running proposal analysis. This can take several seconds.</div>}

      {analysis && <section className="proposal-analysis-result" aria-live="polite">
        <div className="proposal-detail-heading"><div><span className="proposal-status">{analysis.status || 'Status unavailable'}</span><h2>Analysis result</h2></div><span>{analysis.analysis_id ? `Analysis ${analysis.analysis_id}` : ''}</span></div>
        <article className="proposal-recommendation"><h3><Sparkles size={17} /> Recommendation</h3><p>{analysis.recommendation || 'No recommendation was returned.'}</p></article>

        <section className="proposal-analysis-section"><h3><AlertTriangle size={17} /> Risks</h3>
          {analysis.risks?.length ? <ul>{analysis.risks.map((risk, index) => <li key={`${index}-${risk}`}>{typeof risk === 'string' ? risk : JSON.stringify(risk)}</li>)}</ul> : <p>No risks were returned by the API.</p>}
        </section>

        <section className="proposal-analysis-section"><h3><CheckCircle2 size={17} /> Evidence-linked claims</h3>
          {analysis.claims?.length ? analysis.claims.map((claim, index) => <article className="proposal-claim" key={`${claim.statement}-${index}`}>
            <p>{claim.statement || 'Claim text unavailable.'}</p>
            <span>{claim.evidence_status || claim.evidence_classification || 'Evidence status unavailable'}</span>
            {(claim.sources || []).map((source) => <a key={source.source_id} href={source.source_url || undefined} target="_blank" rel="noreferrer">{source.source_title || source.source_id} <ExternalLink size={12} /></a>)}
            {(claim.source_ids || []).filter((id) => !claim.sources?.some((source) => source.source_id === id)).map((id) => <span key={id}>{sourceById.get(id)?.source_title || `Source ${id}`}</span>)}
          </article>) : <p>No factual claims passed evidence verification.</p>}
        </section>

        <section className="proposal-analysis-section"><h3><Search size={17} /> Retrieved evidence and context</h3>
          {evidence.length ? <div className="proposal-evidence-grid">{evidence.map((item, index) => <EvidenceCard key={`${item.source_id}-${item.chunk_index ?? index}`} item={item} />)}</div> : <p>No documentary evidence was returned. The recommendation should be treated conservatively.</p>}
          <small>Relevance assessments are contextual model classifications, not fact verification. External sources describe their named company and do not establish the proposing company’s history. Only sources attached to evidence-checked claims are citations; missing retrieved context does not establish that no contrary evidence exists.</small>
        </section>

        {analysis.customer_feedback_context && <section className="proposal-analysis-section"><h3>Customer feedback signal</h3>
          <p>{analysis.customer_feedback_context.feedback_count ?? 0} proposal-relevant record(s) selected from {analysis.customer_feedback_context.total_company_feedback_available ?? 0} company record(s).</p>
          {analysis.customer_feedback_context.interpretation_warning && <small>{analysis.customer_feedback_context.interpretation_warning}</small>}
        </section>}

        {analysis.external_research && <section className="proposal-analysis-section"><h3>External research</h3><p>Status: {analysis.external_research.status || 'Unavailable'} · Evidence origin: {analysis.external_research.evidence_origin || 'Unavailable'}</p></section>}
        <section className="proposal-analysis-section"><h3>Limitations</h3>
          {analysis.limitations?.length ? <ul>{analysis.limitations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <p>No limitations were returned.</p>}
        </section>
      </section>}

      <p className="proposal-demo-notice">Proposal analysis is generated for this request from the evidence returned by the backend. It is not a company decision. The current API does not provide a proposal history list.</p>
    </div>
  );
}
