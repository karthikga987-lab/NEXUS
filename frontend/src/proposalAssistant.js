const PROPOSAL_WORDS = /\b(proposal(?:s)?|proposed|idea(?:s)?|user[- ]submitted|saved idea)\b/i;
const ANALYSIS_QUESTION_WORDS = /\b(experiment(?:s)?|pilot|trial|risk(?:s)?|concern(?:s)?|recommendation(?:s)?|success metric(?:s)?|metrics?|assumptions?|analysis)\b/i;
const HISTORICAL_QUESTION_WORDS = /\b(launched?|launch|actual(?:ly)?|historical(?:ly)?|documented|announced?|released?|release|shipped?|availability|source|real[- ]world|conducted|performed|ran|completed|observed|discontinued?|shut\s+down|shutdown|service closure|service ended|ceased operations?|product event|company history)\b/i;
const ALL_PROPOSALS_WORDS = /\b(all|list|what proposals|which proposals|have i submitted|show me|my proposals)\b/i;
const NON_MATCH_WORDS = new Set([
  'about', 'after', 'again', 'also', 'analysis', 'company', 'did', 'does',
  'from', 'have', 'identify', 'into', 'motorola', 'my', 'nexus', 'our',
  'proposal', 'proposals', 'recommendation', 'risks', 'saved', 'submitted',
  'the', 'their', 'this', 'what', 'when', 'where', 'which', 'with', 'your',
]);

function words(value) {
  return (String(value || '').toLowerCase().match(/[a-z0-9]+/g) || [])
    .filter((word) => word.length > 2 && !NON_MATCH_WORDS.has(word));
}

function belongsToCompany(proposal, companyId) {
  return !companyId || proposal.company_id === companyId;
}

function scoreProposal(queryWords, proposal) {
  const titleWords = new Set(words(proposal.title));
  const descriptionWords = new Set(words(proposal.description));
  return queryWords.reduce((score, word) => (
    score + (titleWords.has(word) ? 3 : descriptionWords.has(word) ? 1 : 0)
  ), 0);
}

export function classifyAssistantQuestion(query, proposals = [], companyId = '') {
  const companyProposals = proposals.filter((proposal) => belongsToCompany(proposal, companyId));
  const queryWords = words(query);
  const ranked = companyProposals
    .map((proposal) => ({ proposal, score: scoreProposal(queryWords, proposal) }))
    .sort((left, right) => right.score - left.score);
  const titleMatch = ranked.some(({ proposal, score }) => {
    const titleWordSet = new Set(words(proposal.title));
    const titleMatches = queryWords.filter((word) => titleWordSet.has(word));
    return titleMatches.length >= 2 && score >= 6;
  });
  const explicitProposalQuestion = PROPOSAL_WORDS.test(query);
  const analysisQuestion = ANALYSIS_QUESTION_WORDS.test(query);
  const asksAboutProposals = explicitProposalQuestion
    || titleMatch
    || (companyProposals.length > 0 && analysisQuestion && !HISTORICAL_QUESTION_WORDS.test(query));
  const asksAboutHistory = HISTORICAL_QUESTION_WORDS.test(query);

  return {
    asksAboutProposals,
    asksAboutHistory,
    mixed: asksAboutProposals && asksAboutHistory,
    listAll: ALL_PROPOSALS_WORDS.test(query),
  };
}

export function selectSavedProposals(query, proposals = [], companyId = '', intent = null) {
  const companyProposals = proposals.filter((proposal) => belongsToCompany(proposal, companyId));
  if (!companyProposals.length) return [];
  if (intent?.listAll) return companyProposals;

  const queryWords = words(query);
  const ranked = companyProposals
    .map((proposal) => ({ proposal, score: scoreProposal(queryWords, proposal) }))
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score);
  if (ranked.length) return ranked.slice(0, 3).map((item) => item.proposal);

  // General questions about the saved analysis (for example, its risks)
  // refer to the sole company proposal when there is only one. When several
  // exist, show a small recent set instead of silently choosing one.
  return companyProposals.slice(0, companyProposals.length === 1 ? 1 : 3);
}

function sectionsFromDescription(description) {
  const sections = { objective: [], features: [], experiment: [], metrics: [], outcome: [] };
  const headingMap = new Map([
    ['objective', 'objective'],
    ['proposal objective', 'objective'],
    ['goal', 'objective'],
    ['purpose', 'objective'],
    ['proposed features', 'features'],
    ['proposed experiment', 'experiment'],
    ['success metrics', 'metrics'],
    ['expected outcome', 'outcome'],
  ]);
  let active = 'objective';
  for (const line of String(description || '').split(/\r?\n/)) {
    const cleaned = line.trim()
      .replace(/^#{1,6}\s*/, '')
      .replace(/^[-*]\s*/, '')
      .replace(/\*\*/g, '')
      .trim()
    const heading = cleaned.match(/^(proposal objective|objective|goal|purpose|proposed features|proposed experiment|success metrics|expected outcome)\s*:?\s*(.*)$/i);
    if (heading) {
      active = headingMap.get(heading[1].toLowerCase());
      if (heading[2]) sections[active].push(heading[2].trim());
      continue;
    }
    if (cleaned) sections[active].push(cleaned);
  }
  return Object.fromEntries(Object.entries(sections).map(([key, lines]) => [key, lines.join('\n')]));
}

function asAnalysisList(value) {
  if (Array.isArray(value)) return value;
  if (typeof value !== 'string') return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function riskText(risk) {
  if (typeof risk === 'string') return risk;
  return risk?.description || risk?.risk || risk?.statement || JSON.stringify(risk);
}

function recommendationAttribution(analysis) {
  const limitations = asAnalysisList(analysis?.limitations).join(' ');
  return /\bQwen\b/i.test(limitations) ? 'AI-generated by Qwen (saved analysis)' : 'AI-generated saved analysis';
}

export function hasVerifiedProposalClaims(analysis) {
  return (Array.isArray(analysis?.claims) ? analysis.claims : []).some((claim) => (
    claim?.verification_status === 'verified'
    && Array.isArray(claim?.source_ids)
    && claim.source_ids.some((sourceId) => typeof sourceId === 'string' && sourceId.trim())
  ));
}

export function buildSavedProposalAnswer(query, proposals, companyId = '', intent = null) {
  const questionIntent = intent || classifyAssistantQuestion(query, proposals, companyId);
  const selected = selectSavedProposals(query, proposals, companyId, questionIntent);
  if (!selected.length) {
    return {
      companyId,
      proposals: [],
      message: 'No saved proposal records were found for this company. No proposal or historical facts were inferred.',
      historicalProof: false,
    };
  }

  const asksRisks = /\b(risks?|concerns?|limitations?)\b/i.test(query);
  const asksRecommendation = /\b(recommendation|recommend|should we|what did nexus decide)\b/i.test(query);
  const asksExperiment = /\b(experiments?|pilots?|trials?|tests?)\b/i.test(query);
  const asksMetrics = /\b(metrics?|measure|precision|recall|false[- ]positive|user confidence)\b/i.test(query);
  const asksFeatures = /\b(features?|capabilities|objective|purpose)\b/i.test(query);
  const asksForSummary = /\b(summarize|summary|describe|explain|what is|what was|tell me about)\b/i.test(query);
  const isListRequest = questionIntent.listAll;

  const records = selected.map((proposal) => {
    const analysis = (proposal.analyses || []).find(
      (item) => item.accessible && item.status === 'completed',
    ) || (proposal.analyses || []).find((item) => item.accessible);
    const descriptionSections = sectionsFromDescription(proposal.description);
    const blocks = [];

    if (isListRequest) {
      blocks.push({
        label: 'Saved proposal',
        text: `${proposal.title} · ${proposal.workflow_status === 'completed' ? 'analysis completed' : 'submitted'}`,
      });
    } else if (asksRisks) {
      const risks = asAnalysisList(analysis?.risks).map(riskText).filter(Boolean);
      blocks.push({
        label: 'Risks identified by the saved AI analysis',
        text: risks.length ? risks.map((risk) => `• ${risk}`).join('\n') : 'No risks are stored in the accessible saved analysis.',
      });
    } else if (asksRecommendation) {
      blocks.push({
        label: `Saved recommendation · ${recommendationAttribution(analysis)}`,
        text: analysis?.recommendation || 'No recommendation is stored in the accessible saved analysis.',
      });
    } else if (asksExperiment) {
      blocks.push({
        label: 'Experiment described in the user-submitted proposal',
        text: descriptionSections.experiment || 'No proposed experiment is described in this saved proposal.',
      });
      if (asksMetrics && descriptionSections.metrics) {
        blocks.push({ label: 'Success metrics in the proposal', text: descriptionSections.metrics });
      }
    } else if (asksMetrics) {
      blocks.push({
        label: 'Success metrics in the user-submitted proposal',
        text: descriptionSections.metrics || 'No success metrics are described in this saved proposal.',
      });
    } else if (asksFeatures) {
      blocks.push({
        label: 'Proposal objective and features · user-submitted',
        text: [descriptionSections.objective, descriptionSections.features].filter(Boolean).join('\n\n')
          || 'No objective or feature description is stored for this proposal.',
      });
    } else if (asksForSummary || questionIntent.mixed || !asksRisks && !asksRecommendation) {
      blocks.push({
        label: 'Proposal objective · user-submitted content',
        text: descriptionSections.objective || 'No objective text is stored for this proposal.',
      });
      if (descriptionSections.experiment) {
        blocks.push({ label: 'Proposed experiment', text: descriptionSections.experiment });
      }
      if (descriptionSections.metrics) {
        blocks.push({ label: 'Success metrics proposed', text: descriptionSections.metrics });
      }
      const risks = asAnalysisList(analysis?.risks).map(riskText).filter(Boolean);
      if (risks.length) blocks.push({
        label: 'Risks from the saved AI analysis',
        text: risks.map((risk) => `• ${risk}`).join('\n'),
      });
      if (analysis?.recommendation) blocks.push({
        label: `Saved recommendation · ${recommendationAttribution(analysis)}`,
        text: analysis.recommendation,
      });
    }

    return {
      id: proposal.id,
      title: proposal.title,
      description: proposal.description,
      status: proposal.workflow_status || proposal.status || 'submitted',
      analysisId: analysis?.id || null,
      blocks,
    };
  });

  return {
    companyId,
    proposals: records,
    message: isListRequest
      ? `Found ${records.length} saved user-submitted proposal(s) for this company.`
      : `Retrieved ${records.length} company-scoped saved proposal record(s). This is proposal content, not documentary proof of a launch, decision, experiment outcome, or customer feedback.`,
    historicalProof: false,
  };
}
