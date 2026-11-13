const ACTIVE_RESEARCH_STATES = new Set(['queued', 'running']);
const TERMINAL_RESEARCH_STATES = new Set([
  'completed',
  'partial',
  'failed',
  'not_started',
]);

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function stage(status = 'pending', detail = '') {
  return { status, detail };
}

function researchStages(stats) {
  const values = stats?.latest_run?.counts?.workflow_stages;
  return values && typeof values === 'object' ? values : {};
}

/**
 * Coordinate the existing company research/ingestion APIs before proposal
 * analysis. This adds no new evidence path: the final analyzer still reads
 * only company-scoped, persisted records and performs its normal safeguards.
 */
export async function runProposalWorkflow({
  api,
  company,
  proposal,
  includeFreshResearch = false,
  includeInternal = false,
  onStages = () => {},
  onRefreshData = () => {},
  onProposalSaved = () => {},
  pollIntervalMs = 2500,
  maxPolls = 180,
  sleep = wait,
}) {
  const stages = {
    proposal_save: stage(),
    research: stage(),
    ingestion: stage(),
    knowledge_graph: stage(),
    proposal_analysis: stage(),
  };
  const errors = [];
  let latestStats = null;
  let timedOut = false;

  const updateStage = (name, status, detail = '') => {
    stages[name] = stage(status, detail);
    onStages({ ...stages });
  };

  updateStage('proposal_save', 'running', 'Saving this proposal to the selected company.');
  const savedProposal = await api.createProposal({
    company_id: company.id,
    title: proposal.title.trim(),
    description: proposal.description.trim(),
  });
  onProposalSaved(savedProposal);
  updateStage('proposal_save', 'completed', 'Saved; analysis will be attached to this proposal.');
  onRefreshData();

  if (!company.website) {
    updateStage('research', 'skipped', 'No company website is configured.');
  } else {
    try {
      latestStats = await api.companyResearchStats(company.id);
    } catch (error) {
      errors.push(`Research status unavailable: ${error.message}`);
    }

    let researchStatus = latestStats?.research_status;
    if (!ACTIVE_RESEARCH_STATES.has(researchStatus)) {
      updateStage('research', 'running', 'Queueing bounded public company research.');
      try {
        const started = await api.researchCompany(company.id, 6, 3, true);
        researchStatus = started?.status || 'queued';
      } catch (error) {
        // A concurrent onboarding can already own the company worker. Poll
        // its persisted status; other errors remain visible but do not block
        // a conservative analysis of already stored evidence.
        errors.push(`Company research could not be queued: ${error.message}`);
        researchStatus = 'failed';
      }
    } else {
      updateStage('research', 'running', 'Waiting for the company refresh already in progress.');
    }

    if (ACTIVE_RESEARCH_STATES.has(researchStatus)) {
      updateStage('research', 'running', 'Collecting eligible public sources.');
      for (let attempt = 0; attempt < maxPolls; attempt += 1) {
        try {
          latestStats = await api.companyResearchStats(company.id);
          researchStatus = latestStats?.research_status || researchStatus;
          const runningStages = researchStages(latestStats);
          for (const name of ['research', 'ingestion', 'knowledge_graph']) {
            if (runningStages[name]) {
              updateStage(name, runningStages[name]);
            }
          }
          if (TERMINAL_RESEARCH_STATES.has(researchStatus)) break;
        } catch (error) {
          errors.push(`Research progress could not be refreshed: ${error.message}`);
        }
        if (attempt + 1 < maxPolls) await sleep(pollIntervalMs);
      }
      if (ACTIVE_RESEARCH_STATES.has(researchStatus)) {
        timedOut = true;
        errors.push('Company refresh is still running; analysis will use currently persisted evidence.');
        updateStage('research', 'partial', 'Timed out waiting; the company refresh may continue in the background.');
      }
    }

    if (!timedOut && researchStatus === 'completed') {
      const recorded = researchStages(latestStats);
      updateStage('research', recorded.research || 'completed');
      updateStage('ingestion', recorded.ingestion || 'completed');
      updateStage('knowledge_graph', recorded.knowledge_graph || 'completed');
    } else if (!timedOut && researchStatus === 'partial') {
      const recorded = researchStages(latestStats);
      updateStage('research', recorded.research || 'partial');
      updateStage('ingestion', recorded.ingestion || 'partial');
      updateStage('knowledge_graph', recorded.knowledge_graph || 'partial');
      errors.push('Some company refresh stages reported partial results.');
    } else if (!timedOut && researchStatus === 'failed') {
      updateStage('research', 'failed', 'Existing persisted evidence will still be analyzed.');
      errors.push('Company refresh failed; proposal analysis will use existing persisted evidence.');
    }
  }

  // The onboarding worker ingests new sources. A one-time pending-source pass
  // covers sources left pending after a partial worker failure; processed
  // sources are skipped by the existing idempotent ingestion service.
  try {
    const ingestion = await api.companyIngestionStatus(company.id, includeInternal);
    const pendingCount = Number(ingestion?.processing_status_counts?.pending || 0);
    if (pendingCount > 0 && !timedOut) {
      updateStage('ingestion', 'running', `${pendingCount} saved source(s) remain pending.`);
      const processed = await api.processCompanySources(company.id, null, includeInternal);
      const failedCount = Number(processed?.counts?.failed || 0);
      updateStage(
        'ingestion',
        failedCount ? 'partial' : 'completed',
        `${processed?.counts?.processed || 0} processed; ${failedCount} failed.`,
      );
      if (failedCount) errors.push(`${failedCount} source(s) still failed ingestion.`);
    } else if (timedOut) {
      updateStage('ingestion', 'partial', 'Refresh is still running; avoiding a concurrent retry.');
    } else if (stages.ingestion.status === 'pending') {
      updateStage('ingestion', 'completed', 'No pending public documents remain.');
    }
  } catch (error) {
    updateStage('ingestion', 'partial', 'Ingestion status is unavailable; analysis will use persisted evidence.');
    errors.push(`Ingestion status or retry failed: ${error.message}`);
  }

  // The graph endpoint is a projection of persisted events and relationships;
  // the worker extracts supported relationships before this refresh check.
  if (stages.knowledge_graph.status === 'pending') {
    updateStage('knowledge_graph', 'completed', 'Graph data is built from persisted company records.');
  }
  onRefreshData();

  updateStage('proposal_analysis', 'running', 'Retrieving refreshed evidence and analyzing the proposal.');
  try {
    const analysis = await api.analyzeProposal({
      company_id: company.id,
      title: proposal.title.trim(),
      description: proposal.description.trim(),
      proposal_id: savedProposal.id,
      include_fresh_external_research: includeFreshResearch,
      include_authorized_internal: includeInternal,
    });
    updateStage('proposal_analysis', analysis.status || 'completed');
    onRefreshData();
    return {
      analysis,
      proposal: savedProposal,
      refresh: {
        status: errors.length || timedOut ? 'partial' : 'completed',
        timed_out: timedOut,
        errors,
        stages: { ...stages },
      },
    };
  } catch (error) {
    updateStage('proposal_analysis', 'failed', error.message);
    onRefreshData();
    throw error;
  }
}
