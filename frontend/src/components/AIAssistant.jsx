import { useEffect, useState } from 'react';
import { Bot, Send, User, Sparkles, ExternalLink, LoaderCircle } from 'lucide-react';
import { api } from '../api/client';
import { buildSavedProposalAnswer, classifyAssistantQuestion } from '../proposalAssistant';
import './AIAssistant.css';

function ProposalAnswer({ answer }) {
  return <section className="ai-proposal-answer" aria-label="Saved proposal answer">
    <div className="ai-proposal-answer-heading">
      <div><h3>Saved proposal records</h3><p>{answer.message}</p></div>
      <span>Not historical proof</span>
    </div>
    {answer.proposals.map((proposal) => <article className="ai-proposal-record" key={proposal.id}>
      <div className="ai-proposal-record-heading">
        <strong>{proposal.title}</strong>
        <span>{proposal.status.replaceAll('_', ' ')}</span>
      </div>
      {proposal.blocks.map((block, index) => <div className="ai-proposal-block" key={`${block.label}-${index}`}>
        <h4>{block.label}</h4>
        <p>{block.text}</p>
      </div>)}
      <small className="ai-proposal-source-note">Retrieved from saved proposal/analysis records. This content is not a product launch, company decision, completed experiment, or verified customer feedback. No documentary citation is claimed for proposal text.</small>
    </article>)}
  </section>;
}

function HistoricalAnswer({ result, error }) {
  return <section className="ai-historical-answer" aria-label="Historical evidence answer">
    <div className="ai-historical-answer-heading">
      <h3>Documented historical evidence</h3>
      {result?.answer_status && <span>{result.answer_status.replaceAll('_', ' ')}</span>}
    </div>
    {error ? <p role="alert">Historical evidence lookup failed: {error}</p> : <>
      <p>{result?.answer || 'No historical evidence answer was returned.'}</p>
      {result?.requested_aspects?.length > 0 && <ul className="ai-aspects">{result.requested_aspects.map((aspect) => <li key={aspect.aspect}>{aspect.aspect}: {String(aspect.status).replaceAll('_', ' ')}</li>)}</ul>}
      {result?.verified_claims?.map((claim, claimIndex) => <article className="ai-verified-claim" key={`${claim.statement}-${claimIndex}`}>
        <blockquote>{claim.statement}</blockquote>
        {(claim.citations || []).map((citation, citationIndex) => <div key={`${citation.source_id}-${citationIndex}`}>
          <small>{citation.supporting_quote || claim.statement}</small>
          {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">{citation.source_title || 'Open supporting source'} <ExternalLink size={12} /></a>}
        </div>)}
      </article>)}
      {result?.evidence_sources?.length > 0 && <div className="ai-citations"><strong>Historical sources</strong>{result.evidence_sources.map((citation, index) => <a key={`${citation.source_id || citation.source_url}-${index}`} href={citation.source_url || undefined} target="_blank" rel="noreferrer">{citation.source_title || citation.source_url || `Source ${index + 1}`} <ExternalLink size={12} /></a>)}</div>}
      {result?.unsupported_claims?.length > 0 && <small>Claims that did not pass evidence verification were excluded.</small>}
    </>}
  </section>;
}

export default function AIAssistant({ company }) {
  const [message, setMessage] = useState('');
  const [includeInternal, setIncludeInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: `Ask about documented history for ${company?.name || 'this company'}. Answers use available evidence and may report that information is missing.` },
  ]);
  const [proposalHistory, setProposalHistory] = useState([]);
  const [proposalHistoryError, setProposalHistoryError] = useState('');

  useEffect(() => {
    let active = true;
    setProposalHistoryError('');
    api.companyProposals(company.id)
      .then((items) => {
        if (active) {
          setProposalHistory(Array.isArray(items) ? items : []);
          setProposalHistoryError('');
        }
      })
      .catch((requestError) => {
        if (active) setProposalHistoryError(requestError.message || 'Saved proposal context is unavailable.');
      });
    return () => { active = false; };
  }, [company.id]);

  async function handleSend(event) {
    event.preventDefault();
    const query = message.trim();
    if (!query || busy) return;
    setError('');
    setMessages((previous) => [...previous, { role: 'user', text: query }]);
    setMessage('');
    setBusy(true);
    try {
      let savedProposals = proposalHistory;
      let savedProposalError = '';
      try {
        const fetched = await api.companyProposals(company.id);
        savedProposals = Array.isArray(fetched) ? fetched : [];
        setProposalHistory(savedProposals);
        setProposalHistoryError('');
      } catch (historyError) {
        savedProposalError = historyError.message || 'Saved proposal records could not be loaded.';
        setProposalHistoryError(savedProposalError);
      }

      const intent = classifyAssistantQuestion(query, savedProposals, company.id);
      const companyProposalAvailable = savedProposals.some((proposal) => proposal.company_id === company.id);
      const proposalAnswer = intent.asksAboutProposals
        ? (savedProposalError && !companyProposalAvailable
          ? { companyId: company.id, proposals: [], message: `Saved proposal lookup failed: ${savedProposalError}`, historicalProof: false }
          : buildSavedProposalAnswer(query, savedProposals, company.id, intent))
        : null;

      let historicalResult = null;
      let historicalError = '';
      if (intent.asksAboutHistory) {
        try {
          historicalResult = await api.answerQuestion({
            company_id: company.id,
            query,
            limit: 5,
            include_external_public: false,
            include_authorized_internal: includeInternal,
          });
        } catch (historyError) {
          historicalError = historyError.message || 'The evidence answer request failed.';
        }
      }

      setMessages((previous) => [...previous, {
        role: 'assistant',
        text: proposalAnswer ? '' : historicalResult?.answer || 'No answer was returned.',
        status: proposalAnswer ? '' : historicalResult?.answer_status,
        proposalAnswer,
        historicalResult,
        historicalError,
      }]);
    } catch (requestError) {
      setError(requestError.message || 'The evidence answer request failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ai-assistant">
      <div className="ai-welcome">
        <div className="ai-icon"><Sparkles size={25} /></div>
        <div><h2>NEXUS Evidence Assistant</h2><p>Historical questions use verified source passages. Questions about your proposals use saved proposal and analysis records, clearly separated from company history.</p></div>
      </div>
      <div className="ai-chat-window" aria-live="polite">
        {messages.map((item, index) => <div key={`${item.role}-${index}`} className={`ai-message ${item.role}`}>
          <div className="ai-avatar">{item.role === 'assistant' ? <Bot size={19} /> : <User size={19} />}</div>
          <div className="ai-message-content">
            <span>{item.role === 'assistant' ? 'NEXUS AI' : 'You'}{item.status ? ` · ${String(item.status).replaceAll('_', ' ')}` : ''}</span>
            {item.proposalAnswer && <ProposalAnswer answer={item.proposalAnswer} />}
            {(item.historicalResult || item.historicalError) && <HistoricalAnswer result={item.historicalResult} error={item.historicalError} />}
            {!item.proposalAnswer && !item.historicalResult && !item.historicalError && item.text && <p>{item.text}</p>}
          </div>
        </div>)}
        {busy && <div className="ai-message assistant"><div className="ai-avatar"><Bot size={19} /></div><div className="ai-message-content"><span>NEXUS AI</span><p><LoaderCircle className="spin" size={15} /> Checking saved proposal records and documented evidence…</p></div></div>}
      </div>
      {error && <p className="ai-error" role="alert">{error}</p>}
      <form className="ai-input-area" onSubmit={handleSend}>
        <input type="text" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask about company history or a saved proposal…" minLength={3} maxLength={2000} aria-label="Question" />
        <button type="submit" disabled={busy || message.trim().length < 3}><Send size={18} /> Send</button>
      </form>
      <label className="inline-check"><input type="checkbox" checked={includeInternal} onChange={(event) => setIncludeInternal(event.target.checked)} /> Include authorized local documents</label>
      <p className="ai-disclaimer">Historical claims require source evidence. Saved proposal text is hypothetical user input, and saved recommendations or risks are AI analysis rather than documented company facts.</p>
      {proposalHistoryError && <p className="ai-error" role="status">Saved proposal context unavailable: {proposalHistoryError}. Evidence answers remain separate from proposal records.</p>}
    </div>
  );
}
