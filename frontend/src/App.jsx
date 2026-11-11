
import { useEffect, useState } from 'react';
import {
  Activity,
  ArrowUpRight,
  Atom,
  Database,
  Network,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';

import { api } from './api/client';
import CompanyDashboard from './components/CompanyDashboard';

export default function App() {
  const [company, setCompany] = useState('');
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [apiStatus, setApiStatus] = useState('Checking API...');
  const [selectedCompany, setSelectedCompany] = useState(null);

  useEffect(() => {
    api.health()
      .then(() => setApiStatus('API connected'))
      .catch(() => setApiStatus('API offline'));
  }, []);

  useEffect(() => {
    api.companies()
      .then(setItems)
      .catch(() => {});
  }, []);

  async function addCompany(e) {
e.preventDefault();

const companyName = company.trim();

if (!companyName) return;

setBusy(true);
setMessage('');

try {
// First, try creating the company through the real backend.
const created = await api.createCompany({
name: companyName,
});
setItems((old) => [created, ...old]);
setCompany('');
setSelectedCompany(created);
} catch (err) {
  console.error('Company creation failed:', err);

  // Use demo mode only when the backend cannot be reached.
  if (err instanceof TypeError) {
    const demoCompany = {
      id: `demo-${Date.now()}`,
      name: companyName,
      website: '',
      demo: true,
    };

    setItems((old) => [demoCompany, ...old]);
    setCompany('');
    setMessage('Demo workspace created. Backend connection is unavailable.');
    setSelectedCompany(demoCompany);
  } else {
    // Show actual backend errors instead of hiding them.
    setMessage(`Could not create company: ${err.message}`);
  }
} finally {
setBusy(false);
}
}

  function openCompany(item) {
    setSelectedCompany(item);
  }

  function returnHome() {
    setSelectedCompany(null);
  }

  if (selectedCompany) {
    return (
      <CompanyDashboard
        company={selectedCompany}
        onBack={returnHome}
      />
    );
  }

  return (
    <main className="shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <div className="stars" />

      <nav className="nav">
        <button className="brand" onClick={returnHome}>
          <span className="brand-mark">
            <Atom size={21} />
          </span>
          NEXUS
        </button>

        <span className="nav-status">
          <i />
          {apiStatus}
        </span>
      </nav>

      <section className="hero" id="top">
        <div className="eyebrow">
          <Sparkles size={14} />
          PRODUCT KNOWLEDGE & DECISION INTELLIGENCE
        </div>

        <h1>
          Every product decision
          <br />
          <span>leaves a signal.</span>
        </h1>

        <p className="intro">
          Connect company history, product experiments and customer
          feedback. Give your next decision a stronger foundation.
        </p>

        <form className="search-box" onSubmit={addCompany}>
          <Search size={19} />

          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Enter a company name..."
            aria-label="Company name"
          />

          <button disabled={busy}>
            {busy ? 'Creating...' : 'Explore intelligence'}
            <ArrowUpRight size={16} />
          </button>
        </form>

        {message && <p className="notice">{message}</p>}

        <div className="trust-line">
          <ShieldCheck size={14} />
          Evidence-first intelligence · Source-linked insights ·
          Company-specific knowledge
        </div>
      </section>

      <section className="features">
        <article className="feature">
          <div className="feature-icon"><Database /></div>
          <h3>Historical memory</h3>
          <p>
            Bring product events and decisions into one traceable
            knowledge base.
          </p>
        </article>

        <article className="feature">
          <div className="feature-icon"><Network /></div>
          <h3>Connected evidence</h3>
          <p>
            Explore relationships between launches, experiments and
            customer reactions.
          </p>
        </article>

        <article className="feature">
          <div className="feature-icon"><Activity /></div>
          <h3>Decision intelligence</h3>
          <p>
            Compare new proposals with documented historical cases
            and outcomes.
          </p>
        </article>
      </section>

      <section className="workspaces">
        <div className="section-heading">
          <div>
            <span className="eyebrow">YOUR WORKSPACE</span>
            <h2>Companies</h2>
          </div>

          <span className="count">{items.length} saved</span>
        </div>

        {items.length ? (
          <div className="company-list">
            {items.map((item) => (
              <button
                className="company-row"
                key={item.id}
                onClick={() => openCompany(item)}
              >
                <div className="company-avatar">
                  {item.name.slice(0, 1).toUpperCase()}
                </div>

                <div>
                  <strong>{item.name}</strong>
                  <small>{item.website || 'Company workspace'}</small>
                </div>

                <span className="workspace-tag">
                  Open workspace
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="empty">
            Your company workspaces will appear here.
          </div>
        )}
      </section>

      <footer>
        NEXUS
        <span>Evidence before assumptions.</span>
        <small>
          Starter interface · Connect research and intelligence
          modules as they are implemented.
        </small>
      </footer>
    </main>
  );
}
