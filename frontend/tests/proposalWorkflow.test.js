import test from 'node:test';
import assert from 'node:assert/strict';

import { runProposalWorkflow } from '../src/proposalWorkflow.js';

test('proposal submission queues research, waits for ingestion/graph, then analyzes', async () => {
  const calls = [];
  let statsCall = 0;
  const api = {
    createProposal: async (payload) => {
      calls.push(['save', payload.company_id]);
      return { id: 'saved-proposal', company_id: payload.company_id, title: payload.title, description: payload.description, status: 'submitted' };
    },
    companyResearchStats: async (companyId) => {
      calls.push(['stats', companyId]);
      statsCall += 1;
      if (statsCall === 1) return { research_status: 'completed' };
      if (statsCall === 2) return { research_status: 'running' };
      return {
        research_status: 'completed',
        latest_run: { counts: { workflow_stages: {
          research: 'completed', ingestion: 'completed', knowledge_graph: 'completed',
        } } },
      };
    },
    researchCompany: async (...args) => {
      calls.push(['research', ...args]);
      return { status: 'queued' };
    },
    companyIngestionStatus: async (companyId) => {
      calls.push(['ingestion_status', companyId]);
      return { processing_status_counts: { processed: 2 } };
    },
    processCompanySources: async (...args) => {
      calls.push(['process', ...args]);
      return { counts: { processed: 1, failed: 0 } };
    },
    analyzeProposal: async (payload) => {
      calls.push(['analyze', payload.company_id, payload.proposal_id]);
      return { proposal_id: 'proposal-test', analysis_id: 'analysis-test', status: 'completed' };
    },
  };
  let refreshes = 0;
  const result = await runProposalWorkflow({
    api,
    company: { id: 'company-a', name: 'Synthetic Company', website: 'https://company.example' },
    proposal: { title: 'Synthetic proposal', description: 'A clearly labelled synthetic proposal.' },
    sleep: async () => {},
    pollIntervalMs: 0,
    onRefreshData: () => { refreshes += 1; },
  });

  assert.equal(calls[0][0], 'save');
  assert.equal(calls[1][0], 'stats');
  assert.ok(calls.findIndex(([name]) => name === 'research') < calls.findIndex(([name]) => name === 'analyze'));
  assert.equal(calls.at(-1)[0], 'analyze');
  assert.equal(calls.at(-1)[1], 'company-a');
  assert.equal(calls.at(-1)[2], 'saved-proposal');
  assert.equal(result.proposal.id, 'saved-proposal');
  assert.equal(result.analysis.status, 'completed');
  assert.equal(result.refresh.status, 'completed');
  assert.equal(refreshes, 3);
});

test('partial refresh still analyzes only the selected company’s persisted evidence', async () => {
  const calls = [];
  const api = {
    createProposal: async (payload) => {
      calls.push(['save', payload.company_id]);
      return { id: 'saved-company-b', company_id: payload.company_id };
    },
    companyResearchStats: async (companyId) => {
      calls.push(['stats', companyId]);
      return { research_status: 'not_started' };
    },
    researchCompany: async (companyId, _pages, _depth, background) => {
      calls.push(['research', companyId, background]);
      return { status: 'queued' };
    },
    companyIngestionStatus: async (companyId) => {
      calls.push(['ingestion_status', companyId]);
      return { processing_status_counts: {} };
    },
    analyzeProposal: async (payload) => {
      calls.push(['analyze', payload.company_id]);
      return { proposal_id: 'p', analysis_id: 'a', status: 'completed' };
    },
  };
  const results = [
    { research_status: 'failed', latest_run: { counts: { workflow_stages: { research: 'failed' } } } },
  ];
  let pollCount = 0;
  api.companyResearchStats = async (companyId) => {
    calls.push(['stats', companyId]);
    pollCount += 1;
    return pollCount === 1 ? { research_status: 'not_started' } : results[0];
  };

  const result = await runProposalWorkflow({
    api,
    company: { id: 'company-b', name: 'Synthetic B', website: 'https://b.example' },
    proposal: { title: 'Proposal B', description: 'A clearly labelled proposal for company B.' },
    sleep: async () => {},
    pollIntervalMs: 0,
  });

  assert.equal(result.refresh.status, 'partial');
  assert.equal(calls.some(([name, id]) => name === 'analyze' && id === 'company-b'), true);
  assert.equal(calls.some(([name, id]) => id === 'company-a'), false);
});

test('pending persisted sources are processed before final analysis', async () => {
  const calls = [];
  const api = {
    createProposal: async (payload) => ({ id: 'saved-company-c', company_id: payload.company_id }),
    companyResearchStats: async () => ({ research_status: 'completed' }),
    researchCompany: async () => ({ status: 'queued' }),
    companyIngestionStatus: async () => ({ processing_status_counts: { pending: 1 } }),
    processCompanySources: async (companyId) => {
      calls.push(['process', companyId]);
      return { counts: { processed: 1, failed: 0 } };
    },
    analyzeProposal: async ({ company_id }) => {
      calls.push(['analyze', company_id]);
      return { proposal_id: 'p', analysis_id: 'a', status: 'completed' };
    },
  };

  const result = await runProposalWorkflow({
    api,
    company: { id: 'company-c', name: 'Synthetic C', website: 'https://c.example' },
    proposal: { title: 'Proposal C', description: 'A clearly labelled proposal for company C.' },
  });

  assert.deepEqual(calls, [['process', 'company-c'], ['analyze', 'company-c']]);
  assert.equal(result.refresh.stages.ingestion.status, 'completed');
});
