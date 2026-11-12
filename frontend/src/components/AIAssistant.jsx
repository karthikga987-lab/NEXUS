import { useState } from 'react';
import { Bot, Send, User, Sparkles, ExternalLink, LoaderCircle } from 'lucide-react';
import { api } from '../api/client';
import './AIAssistant.css';

export default function AIAssistant({ company }) {
  const [message, setMessage] = useState('');
  const [includeInternal, setIncludeInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [messages, setMessages] = useState([
    { role: 'assistant', text: `Ask about documented history for ${company?.name || 'this company'}. Answers use available evidence and may report that information is missing.` },
  ]);

  async function handleSend(event) {
    event.preventDefault();
    const query = message.trim();
    if (!query || busy) return;
    setError('');
    setMessages((previous) => [...previous, { role: 'user', text: query }]);
    setMessage('');
    setBusy(true);
    try {
      const result = await api.answerQuestion({
        company_id: company.id,
        query,
        limit: 5,
        include_external_public: false,
        include_authorized_internal: includeInternal,
      });
      setMessages((previous) => [...previous, {
        role: 'assistant',
        text: result.answer || 'No answer was returned.',
        status: result.answer_status,
        claims: result.verified_claims || [],
        aspects: result.requested_aspects || [],
        citations: result.evidence_sources || [],
        unsupported: result.unsupported_claims || [],
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
        <div><h2>NEXUS Evidence Assistant</h2><p>Answers are generated from retrieved company evidence. Missing evidence is reported as unavailable.</p></div>
      </div>
      <div className="ai-chat-window" aria-live="polite">
        {messages.map((item, index) => <div key={`${item.role}-${index}`} className={`ai-message ${item.role}`}>
          <div className="ai-avatar">{item.role === 'assistant' ? <Bot size={19} /> : <User size={19} />}</div>
          <div className="ai-message-content">
            <span>{item.role === 'assistant' ? 'NEXUS AI' : 'You'}{item.status ? ` · ${String(item.status).replaceAll('_', ' ')}` : ''}</span>
            <p>{item.text}</p>
            {item.aspects?.length > 0 && <ul className="ai-aspects">{item.aspects.map((aspect) => <li key={aspect.aspect}>{aspect.aspect}: {String(aspect.status).replaceAll('_', ' ')}</li>)}</ul>}
            {item.claims?.map((claim, claimIndex) => <article className="ai-verified-claim" key={`${claim.statement}-${claimIndex}`}>
              <blockquote>{claim.statement}</blockquote>
              {(claim.citations || []).map((citation, citationIndex) => <div key={`${citation.source_id}-${citationIndex}`}>
                <small>{citation.supporting_quote || claim.statement}</small>
                {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">{citation.source_title || 'Open supporting source'} <ExternalLink size={12} /></a>}
              </div>)}
            </article>)}
            {item.citations?.length > 0 && <div className="ai-citations"><strong>Sources</strong>{item.citations.map((citation, citationIndex) => <a key={`${citation.source_id || citation.source_url}-${citationIndex}`} href={citation.source_url || undefined} target="_blank" rel="noreferrer">{citation.source_title || citation.source_url || `Source ${citation.source_id || citationIndex + 1}`} <ExternalLink size={12} /></a>)}</div>}
            {item.unsupported?.length > 0 && <small>Some generated claims did not pass evidence verification and are excluded.</small>}
          </div>
        </div>)}
        {busy && <div className="ai-message assistant"><div className="ai-avatar"><Bot size={19} /></div><div className="ai-message-content"><span>NEXUS AI</span><p><LoaderCircle className="spin" size={15} /> Checking retrieved evidence…</p></div></div>}
      </div>
      {error && <p className="ai-error" role="alert">{error}</p>}
      <form className="ai-input-area" onSubmit={handleSend}>
        <input type="text" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask about documented company history…" minLength={3} maxLength={2000} aria-label="Question" />
        <button type="submit" disabled={busy || message.trim().length < 3}><Send size={18} /> Send</button>
      </form>
      <label className="inline-check"><input type="checkbox" checked={includeInternal} onChange={(event) => setIncludeInternal(event.target.checked)} /> Include authorized local documents</label>
      <p className="ai-disclaimer">Feedback and product pages are evidence only for claims they explicitly support; missing information is not negative evidence.</p>
    </div>
  );
}
