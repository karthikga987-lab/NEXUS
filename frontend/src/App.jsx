
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

const SELECTED_COMPANY_SESSION_KEY = 'nexus.selectedCompanyId';

function readSelectedCompanyId() {
  try {
    return window.sessionStorage.getItem(SELECTED_COMPANY_SESSION_KEY) || '';
  } catch {
    return '';
  }
}

function storeSelectedCompanyId(companyId) {
  try {
    window.sessionStorage.setItem(SELECTED_COMPANY_SESSION_KEY, companyId);
  } catch {
    // The workspace remains usable when browser session storage is unavailable.
  }
}

export default function App() {
  const [company, setCompany] = useState('');
  const [companyWebsite, setCompanyWebsite] = useState('');
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [apiStatus, setApiStatus] = useState('Checking API...');
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [rememberedCompanyId] = useState(readSelectedCompanyId);
  const [loadingCompanies, setLoadingCompanies] = useState(true);
  const [restoringWorkspace, setRestoringWorkspace] = useState(Boolean(rememberedCompanyId));

  useEffect(() => {
    api.health()
      .then(() => setApiStatus('API connected'))
      .catch(() => setApiStatus('API offline'));
  }, []);

  useEffect(() => {
    let active = true;
    api.companies()
      .then((companies) => {
        if (!active) return;
        const savedCompanies = Array.isArray(companies) ? companies : [];
        setItems(savedCompanies);
        if (rememberedCompanyId) {
          const rememberedCompany = savedCompanies.find(
            (item) => item.id === rememberedCompanyId,
          );
          if (rememberedCompany) {
            setSelectedCompany(rememberedCompany);
          } else {
            setMessage('The previously selected company is not available in the company list.');
          }
        }
      })
      .catch((error) => {
        if (active) {
          setMessage(`Company workspaces could not be loaded: ${error.message}`);
        }
      })
      .finally(() => {
        if (active) {
          setLoadingCompanies(false);
          setRestoringWorkspace(false);
        }
      });
    return () => { active = false; };
  }, [rememberedCompanyId]);

  async function addCompany(e) {
e.preventDefault();

const companyName = company.trim();

if (!companyName) return;

setBusy(true);
setMessage('');

try {
const created = await api.createCompany({
name: companyName,
        website: companyWebsite.trim() || null,
});
setItems((old) => [created, ...old]);
setCompany('');
      setCompanyWebsite('');
storeSelectedCompanyId(created.id);
setSelectedCompany(created);
} catch (err) {
      setMessage(`Could not create company: ${err.message}`);
} finally {
setBusy(false);
}
}

  function openCompany(item) {
    storeSelectedCompanyId(item.id);
    setSelectedCompany(item);
  }

  function returnHome() {
    try {
      window.sessionStorage.removeItem(SELECTED_COMPANY_SESSION_KEY);
    } catch {
      // Returning to the company list must not depend on session storage.
    }
    setSelectedCompany(null);
  }

  if (restoringWorkspace) {
    return <main className="shell"><div className="empty" role="status">Restoring selected company workspace…</div></main>;
  }

  if (selectedCompany) {
    return <CompanyDashboard company={selectedCompany} onBack={returnHome} />;
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
            required
            maxLength={255}
          />

          <input
            type="url"
            value={companyWebsite}
            onChange={(e) => setCompanyWebsite(e.target.value)}
            placeholder="Company website (optional)"
            aria-label="Company website"
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

        {loadingCompanies ? (
          <div className="empty" role="status">Loading saved company workspaces…</div>
        ) : items.length ? (
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
        ) : message ? null : (
          <div className="empty">No saved company workspaces are available.</div>
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
