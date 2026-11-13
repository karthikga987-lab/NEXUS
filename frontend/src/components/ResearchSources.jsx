import { useMemo, useState } from 'react';
import "./ResearchSources.css";
import {
  Search, FileText, Globe, Newspaper, BookOpen, CalendarDays,
  ExternalLink, RefreshCw, LoaderCircle, Upload, ShieldCheck, Activity, Tags,
} from 'lucide-react';

function formatDate(value) {
  if (!value) return 'Unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unavailable' : date.toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

function iconForSource(source) {
  const text = `${source.source_type || ''} ${source.publisher || ''}`.toLowerCase();
  if (text.includes('news') || text.includes('press')) return Newspaper;
  if (text.includes('report') || text.includes('filing')) return BookOpen;
  if (text.includes('official') || text.includes('website')) return Globe;
  return FileText;
}

export default function ResearchSources({
  company,
  sources,
  internalSources,
  internalSourcesError = '',
  stats,
  ingestion,
  loading = false,
  actionBusy = '',
  actionMessage = '',
  onResearch,
  onProcess,
  onImportInternal,
}) {
  const [search, setSearch] = useState('');
  const [activeType, setActiveType] = useState('All');
  const [isSynthetic, setIsSynthetic] = useState(false);
  const sourceTypes = ['All', ...new Set((sources || []).map((source) => source.source_type).filter(Boolean))];
  const filteredSources = useMemo(() => (sources || []).filter((source) => {
    const text = `${source.title || ''} ${source.publisher || ''} ${source.url || ''} ${source.source_type || ''}`.toLowerCase();
    return text.includes(search.toLowerCase()) && (activeType === 'All' || source.source_type === activeType);
  }), [sources, search, activeType]);
  const counts = stats?.latest_run?.counts || {};
  const ingestionCounts = ingestion?.processing_status_counts || {};
  const researchFailureCount = stats ? (counts.failed ?? 0) : null;
  const ingestionFailureCount = ingestion ? (ingestionCounts.failed ?? 0) : null;
  const researchSkippedCount = stats
    ? (counts.skipped ?? 0) + (counts.skipped_duplicates ?? 0)
    : null;
  const processedCount = ingestionCounts.processed ?? ingestionCounts.completed ?? null;
  const totalReports = (sources || []).filter((source) => String(source.source_type || "").toLowerCase().includes("report")).length;
  const totalTypes = new Set((sources || []).map((source) => source.source_type).filter(Boolean)).size;

  function handleFile(event) {
    const file = event.target.files?.[0];
    if (file) onImportInternal?.(file, isSynthetic);
    event.target.value = '';
  }

  return (
    <div className="sources-page">
      <div className="sources-summary" aria-label="Saved source summary">
        <div className="sources-summary-card"><span><Activity size={14} />Total sources</span><strong>{sources == null ? "—" : sources.length}</strong></div>
        <div className="sources-summary-card"><span><BookOpen size={14} />Reports</span><strong>{sources == null ? "—" : totalReports}</strong></div>
        <div className="sources-summary-card"><span><Tags size={14} />Source types</span><strong>{sources == null ? "—" : totalTypes}</strong></div>
      </div>
      <section className="research-controls" aria-label="Company research actions">
        <div>
          <h2>Collect company sources</h2>
          <p>Research discovers public source leads and fetches eligible pages using the backend's access and URL safety checks.</p>
        </div>
        <div className="research-action-buttons">
          <button className="secondary-action" type="button" onClick={onResearch} disabled={!!actionBusy || !company?.website}>
            {actionBusy === 'research' ? <><LoaderCircle className="spin" size={16} /> Researching…</> : <><RefreshCw size={16} /> Start research</>}
          </button>
          <button className="secondary-action" type="button" onClick={onProcess} disabled={!!actionBusy || !sources?.length}>
            {actionBusy === 'process' ? <><LoaderCircle className="spin" size={16} /> Processing…</> : 'Process saved sources'}
          </button>
        </div>
        {!company?.website && <small>Add a company website before starting research.</small>}
        {actionMessage && <p className="action-message" role="status">{actionMessage}</p>}
      </section>

      <section className="research-stats-grid" aria-label="Research status and counts">
        <article><span>Research status</span><strong>{stats?.research_status || 'Unavailable'}</strong></article>
        <article><span>URLs discovered</span><strong>{counts.discovered ?? '—'}</strong></article>
        <article><span>Documents collected</span><strong>{counts.collected ?? (sources ? sources.filter((item) => item.content_kind !== 'search_snippet').length : '—')}</strong></article>
        <article><span>Processed</span><strong>{processedCount ?? '—'}</strong></article>
        <article><span>Research fetch failures</span><strong>{researchFailureCount ?? '—'}</strong></article>
        <article><span>Ingestion failures</span><strong>{ingestionFailureCount ?? '—'}</strong></article>
        <article><span>Research URLs skipped</span><strong>{researchSkippedCount ?? '—'}</strong></article>
      </section>
      {stats?.latest_run?.failure_summary && <p className="unavailable-note">Latest research run: {stats.latest_run.failure_summary}</p>}

      <details className="internal-import-panel">
        <summary><ShieldCheck size={17} /> Import authorized local documents</summary>
        <p>Trusted local development only. No API authentication is configured; do not expose this endpoint to a shared or production network.</p>
        <label className="inline-check">
          <input type="checkbox" checked={isSynthetic} onChange={(event) => setIsSynthetic(event.target.checked)} />
          Label this file as synthetic demo data
        </label>
        <label className="file-import-label">
          <Upload size={16} /> Choose .txt or .md document
          <input type="file" accept=".txt,.md,text/plain,text/markdown" onChange={handleFile} disabled={!!actionBusy} />
        </label>
        <p>{internalSources?.length ?? '—'} authorized local document(s) {internalSourcesError ? `· ${internalSourcesError}` : ''}</p>
      </details>

      {internalSources?.length > 0 && <section className="internal-source-list">
        <h2>Authorized local documents</h2>
        {internalSources.map((source) => <article key={source.id}>
          <strong>{source.title || source.original_filename || 'Untitled internal document'}</strong>
          <span>{source.processing_status || 'Status unavailable'} · {source.evidence_origin || 'authorized_internal'}{source.is_synthetic ? ' · SYNTHETIC DEMO' : ''}</span>
        </article>)}
      </section>}

      <div className="sources-toolbar">
        <div className="sources-search">
          <Search size={18} />
          <input type="search" placeholder="Search saved sources…" value={search} onChange={(event) => setSearch(event.target.value)} />
        </div>
        <div className="sources-count"><FileText size={17} />{sources ? `${filteredSources.length} of ${sources.length} sources` : 'Sources unavailable'}</div>
      </div>

      {sourceTypes.length > 1 && <div className="sources-filters">
        {sourceTypes.map((type) => <button key={type} className={activeType === type ? 'sources-filter active' : 'sources-filter'} onClick={() => setActiveType(type)}>{type}</button>)}
      </div>}

      {loading && !sources ? (
        <div className="sources-empty" role="status">Loading source records…</div>
      ) : sources === null || sources === undefined ? (
        <div className="sources-empty" role="alert"><h3>Sources could not be loaded</h3><p>Check the API connection and try again.</p></div>
      ) : filteredSources.length ? (
        <div className="sources-list">
          {filteredSources.map((source) => {
            const SourceIcon = iconForSource(source);
            const originalUrl = source.original_url || source.url;
            const snippetOnly = source.content_kind === 'search_snippet';
            return (
              <article className="source-card" key={source.id}>
                <div className="source-icon"><SourceIcon size={20} /></div>
                <div className="source-details">
                  <div className="source-card-top">
                    <span className="source-type">{source.source_type || 'Source type unavailable'}</span>
                    <span className="source-date"><CalendarDays size={14} />{formatDate(source.publication_date)}</span>
                  </div>
                  <h3>{source.title || 'Untitled source'}</h3>
                  <span className="source-publisher">{source.publisher || 'Publisher unavailable'}</span>
                  <p>{source.processing_status || 'Processing status unavailable'} · {source.evidence_origin || source.permission_status || 'Origin unavailable'}{source.is_synthetic ? ' · SYNTHETIC' : ''}</p>
                  {originalUrl && <a className="source-link" href={originalUrl} target="_blank" rel="noreferrer">Open original source <ExternalLink size={13} /></a>}
                  <div className="source-metadata-line">
                    <span>Event date: {formatDate(source.event_date)}</span>
                    <span>Collected: {formatDate(source.collected_at)}</span>
                    <span>{source.discovery_method || 'Discovery method unavailable'}</span>
                  </div>
                  {snippetOnly && <p className="unavailable-note">Search snippet only. It is a discovery lead, not a collected document or evidence passage.</p>}
                  {source.content_excerpt && <details><summary>Supporting excerpt</summary><blockquote>{source.content_excerpt}</blockquote></details>}
                  {source.processing_status === 'failed' && <p className="unavailable-note">Processing failed{source.processing_failed_stage ? ` during ${source.processing_failed_stage.replaceAll('_', ' ')}` : ''}: {source.processing_error || 'Safe failure details are unavailable.'}</p>}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="sources-empty"><Search size={25} /><h3>No saved sources</h3><p>Start company research to discover publicly accessible sources.</p></div>
      )}

      <p className="sources-demo-notice">Sources shown here come from the company API. Discovery candidates and snippets are not treated as verified company facts.</p>
    </div>
  );
}
