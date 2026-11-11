
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
} from "lucide-react";

const initialProposals = [
  {
    id: 1,
    title: "Introduce AI-Powered Recommendations",
    category: "New Feature",
    status: "Analysed",
    date: "2025-10-15",
    description:
      "Add AI-powered recommendations to help users discover relevant products and features.",
    strengths: [
      "Could improve product discovery.",
      "May increase user engagement.",
    ],
    weaknesses: [
      "Requires reliable recommendation data.",
      "Implementation may require additional resources.",
    ],
    recommendation: "Promising proposal. Validate with a user experiment.",
  },
  {
    id: 2,
    title: "Improve Application Performance",
    category: "Improvement",
    status: "Under Review",
    date: "2025-09-20",
    description:
      "Reduce loading times and improve application responsiveness.",
    strengths: [
      "Addresses reported performance concerns.",
      "Could improve user experience.",
    ],
    weaknesses: [
      "Requires performance investigation.",
    ],
    recommendation: "Prioritise investigation before implementation.",
  },
  {
    id: 3,
    title: "Launch a Customer Feedback Portal",
    category: "New Feature",
    status: "Pending",
    date: "2025-08-12",
    description:
      "Create a dedicated portal for collecting and organising customer feedback.",
    strengths: [
      "Creates a central feedback channel.",
      "Could help identify recurring customer needs.",
    ],
    weaknesses: [
      "Requires ongoing feedback management.",
    ],
    recommendation: "Evaluate the expected adoption and maintenance effort.",
  },
];

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
    return proposals.filter((proposal) => {
      const searchText = search.toLowerCase();

      const matchesSearch =
        proposal.title.toLowerCase().includes(searchText) ||
        proposal.description.toLowerCase().includes(searchText);

      const matchesStatus =
        activeStatus === "All" || proposal.status === activeStatus;

      return matchesSearch && matchesStatus;
    });
  }, [proposals, search, activeStatus]);

  const addProposal = (event) => {
    event.preventDefault();

    if (!title.trim() || !description.trim()) return;

    const newProposal = {
      id: Date.now(),
      title: title.trim(),
      category,
      status: "Pending",
      date: new Date().toISOString().slice(0, 10),
      description: description.trim(),
      strengths: [],
      weaknesses: [],
      recommendation: "Awaiting analysis.",
    };

    setProposals((previous) => [newProposal, ...previous]);
    setTitle("");
    setDescription("");
    setCategory("New Feature");
    setShowForm(false);
    setActiveStatus("All");
    setSearch("");
  };

  const statuses = ["All", "Pending", "Under Review", "Analysed"];

  return (
    <div className="proposal-page">
      <div className="proposal-summary">
        <div className="proposal-summary-card">
          <span>Total Proposals</span>
          <h2>{proposals.length}</h2>
        </div>

        <div className="proposal-summary-card">
          <span>Pending</span>
          <h2>
            {proposals.filter((p) => p.status === "Pending").length}
          </h2>
        </div>

        <div className="proposal-summary-card">
          <span>Under Review</span>
          <h2>
            {proposals.filter((p) => p.status === "Under Review").length}
          </h2>
        </div>

        <div className="proposal-summary-card">
          <span>Analysed</span>
          <h2>
            {proposals.filter((p) => p.status === "Analysed").length}
          </h2>
        </div>
      </div>

      <div className="proposal-actions">
        <div className="proposal-search">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search proposals..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        <button
          className="proposal-add-button"
          onClick={() => setShowForm(!showForm)}
        >
          <Plus size={17} />
          Submit Proposal
        </button>
      </div>

      {showForm && (
        <form className="proposal-form" onSubmit={addProposal}>
          <div className="proposal-form-heading">
            <h3>Submit a Product Proposal</h3>
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
            placeholder="Describe your product proposal..."
            rows={4}
            required
          />

          <button type="submit">Add Proposal</button>
        </form>
      )}

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

      <div className="proposal-list">
        {filteredProposals.length > 0 ? (
          filteredProposals.map((proposal) => (
            <article className="proposal-card" key={proposal.id}>
              <div className="proposal-card-top">
                <span className="proposal-category">
                  {proposal.category}
                </span>
                <span className={`proposal-status ${proposal.status.toLowerCase().replaceAll(" ", "-")}`}>
                  {proposal.status}
                </span>
              </div>

              <h3>{proposal.title}</h3>
              <p>{proposal.description}</p>

              <div className="proposal-card-bottom">
                <span>{proposal.date}</span>
                <button
                  onClick={() => setSelectedProposal(proposal)}
                >
                  View Analysis
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

      {selectedProposal && (
        <div className="proposal-detail">
          <div className="proposal-detail-heading">
            <h3>Proposal Analysis</h3>
            <button onClick={() => setSelectedProposal(null)}>
              <X size={18} />
            </button>
          </div>

          <h2>{selectedProposal.title}</h2>
          <p>{selectedProposal.description}</p>

          <div className="proposal-analysis-section">
            <h4><CheckCircle2 size={17} /> Strengths</h4>
            {selectedProposal.strengths.length > 0 ? (
              selectedProposal.strengths.map((item, index) => (
                <p key={index}>{item}</p>
              ))
            ) : (
              <p>Analysis not available yet.</p>
            )}
          </div>

          <div className="proposal-analysis-section">
            <h4><AlertTriangle size={17} /> Weaknesses</h4>
            {selectedProposal.weaknesses.length > 0 ? (
              selectedProposal.weaknesses.map((item, index) => (
                <p key={index}>{item}</p>
              ))
            ) : (
              <p>Analysis not available yet.</p>
            )}
          </div>

          <div className="proposal-analysis-section">
            <h4><Sparkles size={17} /> Recommendation</h4>
            <p>{selectedProposal.recommendation}</p>
          </div>
        </div>
      )}

      <p className="proposal-demo-notice">
        Demonstration proposals and analysis only. Real proposal
        analysis and AI recommendations will be provided by the
        NEXUS backend after integration.
      </p>
    </div>
  );
}
