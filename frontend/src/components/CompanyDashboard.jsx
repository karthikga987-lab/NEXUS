import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft } from 'lucide-react';

import { api } from '../api/client';
import CompanySidebar from './CompanySidebar';
import CompanyIntelligence, { RAGPanel } from './CompanyIntelligence';
import ProductTimeline from './ProductTimeline';
import ResearchSources from './ResearchSources';
import KnowledgeGraph from './KnowledgeGraph';
import CustomerIntelligence from './CustomerIntelligence';
import ProposalAnalysis from './ProposalAnalysis';
import AIAssistant from './AIAssistant';
import './CompanyDashboard.css';

const sectionTitles = {
  overview: 'Company Overview',
  timeline: 'Product Timeline',
  sources: 'Research Sources',
  graph: 'Knowledge Graph',
  customers: 'Customer Intelligence',
  proposals: 'Proposal Analysis',
  'ai-assistant': 'AI Assistant',
};

function sectionStorageKey(companyId) {
  return `nexus.companySection.${companyId}`;
}

function readInitialSection(companyId) {
  try {
    const storedSection = window.sessionStorage.getItem(sectionStorageKey(companyId));
    return sectionTitles[storedSection] ? storedSection : 'overview';
  } catch {
    return 'overview';
  }
}

function emptyData() {
  return {
    company: null,
    events: null,
    sources: null,
    feedback: null,
    feedbackRecords: null,
    feedbackAnalysis: null,
    ingestion: null,
    graph: null,
    internalSources: null,
    internalSourcesError: '',
    knowledgeItems: null,
    researchStats: null,
    proposals: null,
    errors: [],
  };
}

export default function CompanyDashboard({ company: initialCompany, onBack }) {
  const [company, setCompany] = useState(initialCompany);
  const loadedCompanyId = useRef(initialCompany.id);
  const [activeSection, setActiveSection] = useState(() => readInitialSection(initialCompany.id));
  const [data, setData] = useState(emptyData);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const [includeInternalInViews, setIncludeInternalInViews] = useState(false);
  const [actionBusy, setActionBusy] = useState('');
  const [actionMessage, setActionMessage] = useState('');

  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  function navigateToSection(section) {
    if (!sectionTitles[section]) return;
    try {
      window.sessionStorage.setItem(sectionStorageKey(initialCompany.id), section);
    } catch {
      // Section navigation remains usable when session storage is unavailable.
    }
    setActiveSection(section);
  }

  useEffect(() => {
    let active = true;
    if (loadedCompanyId.current !== initialCompany.id) {
      loadedCompanyId.current = initialCompany.id;
      setCompany(initialCompany);
      setData(emptyData());
    }
    setLoading(true);

    const requests = [
      ['company', api.getCompany],
      ['events', api.companyEvents],
      ['sources', api.companySources],
      ['feedback', api.companyFeedbackTrends],
      ['feedbackRecords', api.companyFeedbackRecords],
      ['feedbackAnalysis', api.companyFeedbackAnalysis],
      ['ingestion', (id) => api.companyIngestionStatus(id, includeInternalInViews)],
      ['graph', api.companyKnowledgeGraph],
      ['internalSources', api.companyInternalSources],
      ['knowledgeItems', (id) => api.companyKnowledgeItems(id, '', includeInternalInViews)],
      ['researchStats', api.companyResearchStats],
      ['proposals', api.companyProposals],
    ];

    Promise.allSettled(requests.map(([, request]) => request(initialCompany.id)))
      .then((results) => {
        if (!active) return;
        const next = emptyData();
        results.forEach((result, index) => {
          const [key] = requests[index];
          if (result.status === 'fulfilled') {
            next[key] = result.value;
          } else if (key === 'internalSources' || key === 'knowledgeItems') {
            next[key] = null;
            if (key === 'internalSources') {
              next.internalSourcesError = result.reason?.message || 'Trusted-local access is unavailable.';
            }
          } else {
            next[key] = null;
            next.errors.push(`${key}: ${result.reason?.message || 'unavailable'}`);
          }
        });
        setData(next);
        if (next.company) setCompany(next.company);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [initialCompany.id, refreshKey, includeInternalInViews]);

  useEffect(() => {
    setDetailsExpanded(false);
    setActionMessage('');
  }, [initialCompany.id]);

  useEffect(() => {
    const status = data.researchStats?.research_status;
    if (status !== 'queued' && status !== 'running') return undefined;

    let active = true;
    const poll = async () => {
      const [researchResult, ingestionResult] = await Promise.allSettled([
        api.companyResearchStats(initialCompany.id),
        api.companyIngestionStatus(initialCompany.id, includeInternalInViews),
      ]);
      if (!active) return;
      setData((current) => {
        const next = { ...current };
        if (researchResult.status === 'fulfilled') next.researchStats = researchResult.value;
        if (ingestionResult.status === 'fulfilled') next.ingestion = ingestionResult.value;
        return next;
      });
      const becameTerminal = researchResult.status === 'fulfilled'
        && !['queued', 'running'].includes(researchResult.value.research_status);
      if (becameTerminal) refresh();
    };

    const timer = window.setInterval(poll, 2500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [data.researchStats?.research_status, initialCompany.id, refresh]);

  async function runAction(kind, message, operation, formatResult) {
    setActionBusy(kind);
    setActionMessage(message);
    try {
      const result = await operation();
      setActionMessage(formatResult(result));
      refresh();
      return result;
    } catch (error) {
      setActionMessage(`${kind === 'research' ? 'Research' : 'Processing'} failed: ${error.message}`);
      return null;
    } finally {
      setActionBusy('');
    }
  }

  const runResearch = () => runAction(
    'research',
    'Checking eligible public URLs. Robots and fetch restrictions are respected.',
    () => api.researchCompany(company.id),
    (result) => {
      const counts = result.counts || {};
      const failures = (result.results || [])
        .filter((item) => item.status === 'failed')
        .slice(0, 3)
        .map((item) => `${item.url || 'URL unavailable'}: ${item.reason || 'Failure reason unavailable'}`);
      const failureText = failures.length ? ` Failures: ${failures.join(' · ')}` : '';
      const discoveryText = result.discovery_errors?.length
        ? ` Discovery: ${result.discovery_errors.slice(0, 2).join(' · ')}`
        : '';
      return `Research ${result.status || 'finished'}: ${counts.discovered ?? 0} discovered, ${counts.collected ?? 0} full documents, ${counts.failed ?? 0} fetch failures, ${counts.skipped ?? 0} skipped, ${counts.skipped_duplicates ?? 0} duplicate URLs skipped.${failureText}${discoveryText}`;
    },
  );

  const runProcess = (includeInternal = false) => runAction(
    includeInternal ? 'internal-process' : 'process',
    'Processing saved documents with the configured AI services.',
    () => api.processCompanySources(company.id, null, includeInternal),
    (result) => {
      const counts = result.counts || {};
      return `Processing ${result.status || 'finished'}: ${counts.processed ?? 0} processed, ${counts.failed ?? 0} failed, ${counts.skipped ?? 0} skipped.`;
    },
  );

  async function importInternalSource(file, isSynthetic) {
    setActionBusy('internal-import');
    setActionMessage('Importing an authorized local document. The backend enforces loopback access.');
    try {
      await api.importInternalSource(company.id, file, { isSynthetic });
      setActionMessage(`Imported ${file.name}. Process local documents to extract evidence and embeddings.`);
      refresh();
    } catch (error) {
      setActionMessage(`Local import unavailable: ${error.message}`);
    } finally {
      setActionBusy('');
    }
  }

  async function submitFeedback(payload) {
    const result = await api.submitFeedback(payload);
    refresh();
    return result;
  }

  return (
    <div className="company-dashboard">
      <CompanySidebar activeSection={activeSection} onNavigate={navigateToSection} />
      <main className="dashboard-main">
        <header className="dashboard-topbar">
          <button className="back-button" type="button" onClick={onBack}>
            <ArrowLeft size={16} /> Back to Companies
          </button>
          <div className="dashboard-breadcrumb">NEXUS <span>/</span> {company.name}</div>
          <span className={`research-status ${data.researchStats?.research_status || ''}`}>
            {data.researchStats?.research_status || 'Research status unavailable'}
          </span>
        </header>

        <section className="dashboard-content">
          <div className="dashboard-heading">
            <div>
              <p className="dashboard-eyebrow">COMPANY INTELLIGENCE</p>
              <h1>{company.name}</h1>
              <p className="dashboard-subtitle">{sectionTitles[activeSection]}</p>
            </div>
          </div>

          {activeSection === 'overview' && (
            <>
              <CompanyIntelligence
                company={company}
                data={data}
                loading={loading}
                expanded={detailsExpanded}
                onToggle={() => setDetailsExpanded((value) => !value)}
                onResearch={runResearch}
                onProcess={() => runProcess(false)}
                actionBusy={actionBusy}
                actionMessage={actionMessage}
                onSubmitFeedback={submitFeedback}
                onOpenProposals={() => navigateToSection('proposals')}
                onImportInternal={importInternalSource}
                onProcessInternal={() => runProcess(true)}
                includeInternalInViews={includeInternalInViews}
                onToggleInternalInViews={setIncludeInternalInViews}
              />
              <RAGPanel companyId={company.id} companyName={company.name} />
            </>
          )}
          {activeSection === 'timeline' && <ProductTimeline events={data.events} sources={data.sources || []} loading={loading} />}
          {activeSection === 'sources' && (
            <ResearchSources
              company={company}
              sources={data.sources}
              internalSources={data.internalSources}
              internalSourcesError={data.internalSourcesError}
              stats={data.researchStats}
              ingestion={data.ingestion}
              loading={loading}
              actionBusy={actionBusy}
              actionMessage={actionMessage}
              onResearch={runResearch}
              onProcess={() => runProcess(false)}
              onImportInternal={importInternalSource}
              onRefresh={refresh}
            />
          )}
          {activeSection === 'graph' && <KnowledgeGraph graph={data.graph} loading={loading} />}
          {activeSection === 'customers' && (
            <CustomerIntelligence
              companyId={company.id}
              feedback={data.feedback}
              feedbackRecords={data.feedbackRecords}
              analysis={data.feedbackAnalysis}
              loading={loading}
              onSubmitFeedback={submitFeedback}
            />
          )}
          {activeSection === 'proposals' && (
            <ProposalAnalysis company={company} onRefreshData={refresh} />
          )}
          {activeSection === 'ai-assistant' && <AIAssistant company={company} />}
          {data.errors.length > 0 && (
            <p className="dashboard-load-warning" role="alert">
              Some company data could not be loaded. Unavailable data is not an empty result: {data.errors.join('; ')}
            </p>
          )}
        </section>
      </main>
    </div>
  );
}
