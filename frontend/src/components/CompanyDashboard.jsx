
import { useState } from "react";
import { ArrowLeft, Bell, Search, Settings } from 'lucide-react';

import CompanySidebar from "./CompanySidebar";
import ProductTimeline from "./ProductTimeline";
import ResearchSources from "./ResearchSources";
import KnowledgeGraph from "./KnowledgeGraph";
import CustomerIntelligence from "./CustomerIntelligence";
import ProposalAnalysis from "./ProposalAnalysis";
import AIAssistant from "./AIAssistant";
import "./CompanyDashboard.css";

export default function CompanyDashboard({ company, onBack }) {
  const [activeSection, setActiveSection] = useState("overview");

  const sectionTitles = {
    overview: "Company Overview",
    timeline: "Product Timeline",
    sources: "Research Sources",
    graph: "Knowledge Graph",
    customers: "Customer Intelligence",
    proposals: "Proposal Analysis",
    "ai-assistant": "AI Assistant",
  };

  return (
    <div className="company-dashboard">
      <CompanySidebar onNavigate={setActiveSection} />

      <main className="dashboard-main">
        <header className="dashboard-topbar">
            <button className="back-button" onClick={onBack}>

                <ArrowLeft size={16} />
                Back to Companies
                </button>
          <div className="dashboard-breadcrumb">
            NEXUS <span>/</span> Workspace
          </div>

          <div className="dashboard-actions">
            <button aria-label="Search">
              <Search size={19} />
            </button>
            <button aria-label="Notifications">
              <Bell size={19} />
            </button>
            <button aria-label="Settings">
              <Settings size={19} />
            </button>
          </div>
        </header>

        <section className="dashboard-content">
          <div className="dashboard-heading">
            <div>
              <p className="dashboard-eyebrow">
                COMPANY INTELLIGENCE
              </p>

              <h1>{company?.name || "Company Workspace"}</h1>

              <p className="dashboard-subtitle">
                {sectionTitles[activeSection]}
              </p>
            </div>

            <span className="research-status">
              Research pending
            </span>
          </div>

          {activeSection === "overview" ? (
  <div className="overview-content">

    <div className="overview-stats">

      <div className="overview-card">
        <span>Product Events</span>
        <h2>24</h2>
        <p>Historical product activities</p>
      </div>

      <div className="overview-card">
        <span>Research Sources</span>
        <h2>18</h2>
        <p>Documents and articles</p>
      </div>

      <div className="overview-card">
        <span>Customer Feedback</span>
        <h2>156</h2>
        <p>Feedback entries</p>
      </div>

      <div className="overview-card">
        <span>Proposals Analysed</span>
        <h2>5</h2>
        <p>Product proposals</p>
      </div>

    </div>

    <div className="overview-bottom">

      <div className="overview-panel">
        <h2>Recent Activity</h2>
        <p>No real activity loaded yet.</p>
        <p>Recent product events will appear here.</p>
      </div>

      <div className="overview-panel">
        <h2>Research Status</h2>
        <span className="research-status">
          Awaiting backend integration
        </span>
        <p>Company research will appear here once connected.</p>
      </div>

    </div>

    <p className="demo-notice">
      Demonstration metrics only. Real company intelligence
      will be displayed after backend integration.
    </p>

  </div>
) : activeSection === "timeline" ? (
  <ProductTimeline />
) : activeSection === "sources" ? (
  <ResearchSources />
) : activeSection === "graph" ? (
  <KnowledgeGraph />
) : activeSection === "customers" ? (
  <CustomerIntelligence />
) : activeSection === "proposals" ? (
  <ProposalAnalysis />
) : activeSection === "ai-assistant" ? (
  <AIAssistant company={company} />
) : (
  <div className="dashboard-placeholder">
    <h2>{sectionTitles[activeSection]}</h2>
    <p>
      This section is under development.
      Its content will be connected to the NEXUS backend.
    </p>
  </div>
)}
        </section>
      </main>
    </div>
  );
}
