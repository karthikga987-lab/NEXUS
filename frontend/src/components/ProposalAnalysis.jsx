

import { useMemo, useState } from "react";
import {
  Search,
  Plus,
  Lightbulb,
  CheckCircle2,
  AlertTriangle,
  Clock,
  X,
  Sparkles,
  Target,
  TrendingUp,
  ShieldCheck,
  Zap,
  BarChart3,
  ArrowUpRight,
  CalendarDays,
  ClipboardCheck,
} from "lucide-react";
import "./ProposalAnalysis.css";

const initialProposals = [
  {
    id: 1,
    title: "Introduce AI-Powered Recommendations",
    category: "New Feature",
    status: "Analysed",
    date: "2025-10-15",
    score: 88,
    criteria: {
      strategicFit: 92,
      feasibility: 78,
      innovation: 94,
      customerValue: 89,
    },
    description:
      "Add AI-powered recommendations to help users discover relevant products and features.",
    strengths: [
      "Could improve product discovery.",
      "May increase user engagement.",
      "Supports the product's intelligent automation strategy.",
    ],
    weaknesses: [
      "Requires reliable recommendation data.",
      "Implementation may require additional resources.",
    ],
    risks: [
      "Recommendation quality depends on available customer data.",
    ],
    recommendation:
      "Promising proposal. Validate with a user experiment before full implementation.",
  },
  {
    id: 2,
    title: "Improve Application Performance",
    category: "Improvement",
    status: "Under Review",
    date: "2025-09-20",
    score: 76,
    criteria: {
      strategicFit: 85,
      feasibility: 72,
      innovation: 65,
      customerValue: 82,
    },
    description:
      "Reduce loading times and improve application responsiveness.",
    strengths: [
      "Addresses reported performance concerns.",
      "Could improve user experience.",
      "May reduce customer frustration.",
    ],
    weaknesses: [
      "Requires performance investigation.",
      "The root cause of delays is not yet established.",
    ],
    risks: [
      "Optimisation work could affect existing functionality.",
    ],
    recommendation:
      "Prioritise investigation and performance benchmarking before implementation.",
  },
  {
    id: 3,
    title: "Launch a Customer Feedback Portal",
    category: "New Feature",
    status: "Pending",
    date: "2025-08-12",
    score: 0,
    criteria: null,
    description:
      "Create a dedicated portal for collecting and organising customer feedback.",
    strengths: [],
    weaknesses: [],
    risks: [],
    recommendation: "Awaiting evaluation.",
  },
];

const statuses = ["All", "Pending", "Under Review", "Analysed"];

const criteriaConfig = [
  { key: "strategicFit", label: "Strategic Fit", icon: Target },
  { key: "feasibility", label: "Feasibility", icon: CheckCircle2 },
  { key: "innovation", label: "Innovation", icon: Zap },
  { key: "customerValue", label: "Customer Value", icon: UsersIcon },
];

function UsersIcon(props) {
  return <ClipboardCheck {...props} />;
}

function getScoreLabel(score) {
  if (score >= 85) return "Strong";
  if (score >= 70) return "Promising";
  if (score > 0) return "Needs Review";
  return "Not evaluated";
}

export default function ProposalAnalysis() {
  const [proposals, setProposals] = useState(initialProposals);
  const [search, setSearch] = useState("");
  const [activeStatus, setActiveStatus] = useState("All");
  const [selectedProposal, setSelectedProposal] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("New Feature");

  const filteredProposals = useMemo(() => {
    const query = search.toLowerCase().trim();

    return proposals.filter((proposal) => {
      const matchesSearch =
        proposal.title.toLowerCase().includes(query) ||
        proposal.description.toLowerCase().includes(query) ||
        proposal.category.toLowerCase().includes(query);

      const matchesStatus =
        activeStatus === "All" || proposal.status === activeStatus;

      return matchesSearch && matchesStatus;
    });
  }, [proposals, search, activeStatus]);

  const counts = useMemo(
    () => ({
      total: proposals.length,
      pending: proposals.filter((p) => p.status === "Pending").length,
      review: proposals.filter((p) => p.status === "Under Review").length,
      analysed: proposals.filter((p) => p.status === "Analysed").length,
    }),
    [proposals]
  );

  const evaluatedProposals = proposals.filter(
    (proposal) => proposal.status === "Analysed" && proposal.score > 0
  );

  const averageScore = evaluatedProposals.length
    ? Math.round(
        evaluatedProposals.reduce((sum, proposal) => sum + proposal.score, 0) /
          evaluatedProposals.length
      )
    : 0;

  const addProposal = (event) => {
    event.preventDefault();

    if (!title.trim() || !description.trim()) return;

    const newProposal = {
      id: Date.now(),
      title: title.trim(),
      category,
      status: "Pending",
      date: new Date().toISOString().slice(0, 10),
      score: 0,
      criteria: null,
      description: description.trim(),
      strengths: [],
      weaknesses: [],
      risks: [],
      recommendation: "Awaiting evaluation.",
    };

    setProposals((previous) => [newProposal, ...previous]);
    setTitle("");
    setDescription("");
    setCategory("New Feature");
    setShowForm(false);
    setActiveStatus("All");
    setSearch("");
  };

  const statusClass = (status) =>
    status.toLowerCase().replaceAll(" ", "-");

  return (
    <div className="proposal-page">
      <header className="proposal-heading">
        <div>
          <div className="proposal-eyebrow">
            <Sparkles size={14} />
            AI DECISION INTELLIGENCE
          </div>
          <h2>Proposal Analysis</h2>
          <p>
            Evaluate product ideas, identify risks, and discover
            opportunities for better product decisions.
          </p>
        </div>

        <div className="proposal-demo-label">
          <span />
          Demo evaluation data
        </div>
      </header>

      {/* OVERVIEW METRICS */}
      <section className="proposal-summary">
        <div className="proposal-summary-card">
          <div className="proposal-summary-top">
            <span>Total Proposals</span>
            <Lightbulb size={18} />
          </div>
          <h2>{counts.total}</h2>
          <p>Ideas submitted</p>
        </div>

        <div className="proposal-summary-card">
          <div className="proposal-summary-top">
            <span>Pending</span>
            <Clock size={18} />
          </div>
          <h2>{counts.pending}</h2>
          <p>Awaiting evaluation</p>
        </div>

        <div className="proposal-summary-card">
          <div className="proposal-summary-top">
            <span>Under Review</span>
            <BarChart3 size={18} />
          </div>
          <h2>{counts.review}</h2>
          <p>Currently being reviewed</p>
        </div>

        <div className="proposal-summary-card">
          <div className="proposal-summary-top">
            <span>Analysed</span>
            <ShieldCheck size={18} />
          </div>
          <h2>{counts.analysed}</h2>
          <p>Completed evaluations</p>
        </div>
      </section>

      {/* EVALUATION OVERVIEW */}
      <section className="proposal-insights">
        <div className="proposal-insight-card average-score-card">
          <div className="proposal-section-heading">
            <div>
              <h3>Average Evaluation Score</h3>
              <p>Across completed demo evaluations</p>
            </div>
            <TrendingUp size={19} />
          </div>

          <div className="average-score-content">
            <div
              className="proposal-score-ring"
              style={{
                background: `conic-gradient(#ae8bff ${averageScore * 3.6}deg, rgba(255,255,255,0.08) 0deg)`,
              }}
            >
              <div className="proposal-score-ring-inner">
                <strong>{averageScore}</strong>
                <span>/ 100</span>
              </div>
            </div>

            <div className="average-score-description">
              <span className="score-status">{getScoreLabel(averageScore)}</span>
              <p>
                {evaluatedProposals.length} completed evaluation
                {evaluatedProposals.length === 1 ? "" : "s"} included.
              </p>
            </div>
          </div>
        </div>

        <div className="proposal-insight-card status-overview-card">
          <div className="proposal-section-heading">
            <div>
              <h3>Proposal Pipeline</h3>
              <p>Current distribution by status</p>
            </div>
            <BarChart3 size={19} />
          </div>

          <div className="pipeline-list">
            {[
              { label: "Analysed", count: counts.analysed, color: "analysed" },
              { label: "Under Review", count: counts.review, color: "review" },
              { label: "Pending", count: counts.pending, color: "pending" },
            ].map((item) => (
              <div className="pipeline-item" key={item.label}>
                <div className="pipeline-label">
                  <span>{item.label}</span>
                  <strong>{item.count}</strong>
                </div>
                <div className="pipeline-track">
                  <div
                    className={`pipeline-fill ${item.color}`}
                    style={{
                      width: `${counts.total ? (item.count / counts.total) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PROPOSAL EXPLORER */}
      <section className="proposal-workspace">
        <div className="proposal-workspace-heading">
          <div>
            <h3>Proposal Workspace</h3>
            <p>Review submitted ideas and inspect their evaluations.</p>
          </div>

          <button
            className="proposal-add-button"
            onClick={() => setShowForm((previous) => !previous)}
          >
            <Plus size={17} />
            Submit Proposal
          </button>
        </div>

        {showForm && (
          <form className="proposal-form" onSubmit={addProposal}>
            <div className="proposal-form-heading">
              <div>
                <h3>Submit a Product Proposal</h3>
                <p>Add a new idea to the evaluation pipeline.</p>
              </div>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                aria-label="Close form"
              >
                <X size={18} />
              </button>
            </div>

            <label htmlFor="proposal-title">Proposal Title</label>
            <input
              id="proposal-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Enter proposal title"
              required
            />

            <label htmlFor="proposal-category">Category</label>
            <select
              id="proposal-category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option>New Feature</option>
              <option>Improvement</option>
              <option>Bug Fix</option>
              <option>Research</option>
            </select>

            <label htmlFor="proposal-description">Description</label>
            <textarea
              id="proposal-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe the problem, proposed solution, and expected value..."
              rows={4}
              required
            />

            <button type="submit" className="proposal-form-submit">
              <Plus size={16} />
              Add Proposal
            </button>
          </form>
        )}

        <div className="proposal-toolbar">
          <div className="proposal-search">
            <Search size={17} />
            <input
              type="text"
              placeholder="Search proposals..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <div className="proposal-filters">
            {statuses.map((status) => (
              <button
                key={status}
                className={
                  activeStatus === status
                    ? "proposal-filter active"
                    : "proposal-filter"
                }
                onClick={() => setActiveStatus(status)}
              >
                {status}
              </button>
            ))}
          </div>
        </div>

        <div className="proposal-list">
          {filteredProposals.length > 0 ? (
            filteredProposals.map((proposal) => (
              <article className="proposal-card" key={proposal.id}>
                <div className="proposal-card-top">
                  <span className="proposal-category">
                    {proposal.category}
                  </span>

                  <span className={`proposal-status ${statusClass(proposal.status)}`}>
                    {proposal.status}
                  </span>
                </div>

                <div className="proposal-card-main">
                  <div className="proposal-card-copy">
                    <h3>{proposal.title}</h3>
                    <p>{proposal.description}</p>
                  </div>

                  <div className="proposal-card-score">
                    <span>Evaluation</span>
                    <strong>
                      {proposal.score > 0 ? proposal.score : "—"}
                      {proposal.score > 0 && <small>/100</small>}
                    </strong>
                    <span>{getScoreLabel(proposal.score)}</span>
                  </div>
                </div>

                {proposal.criteria && (
                  <div className="proposal-mini-criteria">
                    {criteriaConfig.map((criterion) => (
                      <div key={criterion.key}>
                        <span>{criterion.label}</span>
                        <strong>
                          {proposal.criteria[criterion.key]}%
                        </strong>
                      </div>
                    ))}
                  </div>
                )}

                <div className="proposal-card-bottom">
                  <span>
                    <CalendarDays size={14} />
                    {proposal.date}
                  </span>

                  <button onClick={() => setSelectedProposal(proposal)}>
                    View Analysis
                    <ArrowUpRight size={15} />
                  </button>
                </div>
              </article>
            ))
          ) : (
            <div className="proposal-empty">
              <Search size={25} />
              <h3>No proposals found</h3>
              <p>Try another search or status filter.</p>
            </div>
          )}
        </div>
      </section>

      <div className="proposal-demo-notice">
        <Sparkles size={15} />
        Demonstration evaluations only. Real scoring, evidence validation,
        risk analysis, and AI recommendations will be supplied by the NEXUS
        intelligence backend after integration.
      </div>

      {/* ANALYSIS DETAILS */}
      {selectedProposal && (
        <div
          className="proposal-modal-overlay"
          onClick={() => setSelectedProposal(null)}
        >
          <div
            className="proposal-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="proposal-detail-heading">
              <div>
                <span className="proposal-eyebrow">PROPOSAL EVALUATION</span>
                <h3>{selectedProposal.title}</h3>
              </div>
              <button
                onClick={() => setSelectedProposal(null)}
                aria-label="Close analysis"
              >
                <X size={19} />
              </button>
            </div>

            <div className="proposal-detail-meta">
              <span className="proposal-category">
                {selectedProposal.category}
              </span>
              <span className={`proposal-status ${statusClass(selectedProposal.status)}`}>
                {selectedProposal.status}
              </span>
              <span className="proposal-detail-date">
                <CalendarDays size={14} />
                {selectedProposal.date}
              </span>
            </div>

            <p className="proposal-detail-description">
              {selectedProposal.description}
            </p>

            {selectedProposal.criteria ? (
              <>
                <div className="proposal-detail-score">
                  <div>
                    <span>Overall Evaluation Score</span>
                    <strong>{selectedProposal.score}<small>/100</small></strong>
                  </div>
                  <span className="score-status">
                    {getScoreLabel(selectedProposal.score)}
                  </span>
                </div>

                <div className="proposal-analysis-section">
                  <h4><Target size={17} /> Evaluation Criteria</h4>
                  <div className="proposal-criteria-grid">
                    {criteriaConfig.map((criterion) => {
                      const CriterionIcon = criterion.icon;
                      return (
                        <div className="proposal-criterion" key={criterion.key}>
                          <div>
                            <CriterionIcon size={15} />
                            <span>{criterion.label}</span>
                            <strong>
                              {selectedProposal.criteria[criterion.key]}%
                            </strong>
                          </div>
                          <div className="criterion-track">
                            <div
                              style={{
                                width: `${selectedProposal.criteria[criterion.key]}%`,
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="proposal-analysis-section">
                  <h4><CheckCircle2 size={17} /> Strengths</h4>
                  {selectedProposal.strengths.map((item, index) => (
                    <p className="analysis-point" key={index}>{item}</p>
                  ))}
                </div>

                <div className="proposal-analysis-section">
                  <h4><AlertTriangle size={17} /> Weaknesses</h4>
                  {selectedProposal.weaknesses.map((item, index) => (
                    <p className="analysis-point" key={index}>{item}</p>
                  ))}
                </div>

                <div className="proposal-analysis-section">
                  <h4><ShieldCheck size={17} /> Potential Risks</h4>
                  {selectedProposal.risks.map((item, index) => (
                    <p className="analysis-point" key={index}>{item}</p>
                  ))}
                </div>
              </>
            ) : (
              <div className="proposal-awaiting">
                <Clock size={20} />
                <div>
                  <strong>Evaluation pending</strong>
                  <p>This proposal has not yet received an evaluation.</p>
                </div>
              </div>
            )}

            <div className="proposal-recommendation">
              <h4><Sparkles size={17} /> Recommendation</h4>
              <p>{selectedProposal.recommendation}</p>
            </div>

            <p className="proposal-modal-demo">
              Illustrative evaluation. Not an actual AI-generated decision.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

