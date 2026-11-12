import { useMemo, useState } from 'react';
import { Search, MessageSquare, ThumbsUp, ThumbsDown, Minus, TrendingUp } from 'lucide-react';

const sentimentIcons = { positive: ThumbsUp, negative: ThumbsDown, neutral: Minus, mixed: Minus, unknown: Minus };
const sentimentFilters = ['All', 'Positive', 'Negative', 'Neutral', 'Mixed', 'Unknown'];

export default function CustomerIntelligence({ companyId, feedback, analysis, loading = false, onSubmitFeedback }) {
  const [search, setSearch] = useState('');
  const [activeSentiment, setActiveSentiment] = useState('All');
  const [selectedFeedback, setSelectedFeedback] = useState(null);
  const [text, setText] = useState('');
  const [productName, setProductName] = useState('');
  const [rating, setRating] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formMessage, setFormMessage] = useState('');

  const records = useMemo(() => {
    const byId = new Map();
    (feedback?.trends || []).forEach((trend) => (trend.evidence || []).forEach((item) => {
      const id = item.feedback_id || `${trend.topic}:${item.feedback_text}`;
      const existing = byId.get(id);
      if (existing) {
        existing.topics = [...new Set([...existing.topics, trend.topic])];
      } else {
        byId.set(id, { ...item, topics: [trend.topic] });
      }
    }));
    return [...byId.values()];
  }, [feedback]);

  const filteredFeedback = useMemo(() => records.filter((item) => {
    const sentiment = String(item.sentiment || 'unknown').toLowerCase();
    const text = `${item.feedback_text || ''} ${item.product_name || ''} ${(item.topics || []).join(' ')}`.toLowerCase();
    const selected = activeSentiment === 'All' || sentiment === activeSentiment.toLowerCase();
    return selected && text.includes(search.toLowerCase());
  }), [records, search, activeSentiment]);

  const distribution = analysis?.sentiment_distribution || {};
  const positiveCount = distribution.positive ?? records.filter((item) => item.sentiment === 'positive').length;
  const negativeCount = distribution.negative ?? records.filter((item) => item.sentiment === 'negative').length;
  const neutralCount = distribution.neutral ?? records.filter((item) => item.sentiment === 'neutral').length;

  async function submit(event) {
    event.preventDefault();
    if (!text.trim()) return;
    setSubmitting(true);
    setFormMessage('');
    try {
      await onSubmitFeedback({
        company_id: companyId,
        text: text.trim(),
        product_name: productName.trim() || null,
        rating: rating === '' ? null : Number(rating),
      });
      setText('');
      setProductName('');
      setRating('');
      setFormMessage('Feedback saved. Its topic and sentiment labels are heuristic.');
    } catch (error) {
      setFormMessage(`Feedback was not saved: ${error.message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="customer-page">
      <div className="customer-stats">
        <div className="customer-stat-card"><span>Total Feedback</span><h2>{feedback?.total_feedback ?? '—'}</h2><p>{feedback ? 'Company-submitted records' : 'Unavailable'}</p></div>
        <div className="customer-stat-card"><span>Positive</span><h2>{feedback ? positiveCount : '—'}</h2><p>Heuristic sentiment</p></div>
        <div className="customer-stat-card"><span>Negative</span><h2>{feedback ? negativeCount : '—'}</h2><p>Heuristic sentiment</p></div>
        <div className="customer-stat-card"><span>Neutral</span><h2>{feedback ? neutralCount : '—'}</h2><p>Heuristic sentiment</p></div>
      </div>

      <section className="feedback-submit-panel">
        <div className="detail-section-title"><TrendingUp size={18} /><h3>Submit customer feedback</h3></div>
        <form onSubmit={submit}>
          <label>Feedback text<textarea value={text} onChange={(event) => setText(event.target.value)} maxLength={10000} required rows={3} /></label>
          <div className="feedback-submit-fields">
            <label>Product (optional)<input value={productName} onChange={(event) => setProductName(event.target.value)} maxLength={255} /></label>
            <label>Rating (optional)<input type="number" min="0" max="5" step="0.5" value={rating} onChange={(event) => setRating(event.target.value)} /></label>
          </div>
          <button type="submit" disabled={submitting || !text.trim()}>{submitting ? 'Saving…' : 'Save feedback'}</button>
          {formMessage && <p role="status">{formMessage}</p>}
        </form>
        <small>Feedback represents user-submitted experience. Classification is heuristic and is not documentary proof of a product event or outcome.</small>
      </section>

      <div className="customer-toolbar">
        <div className="customer-search"><Search size={18} /><input type="search" placeholder="Search submitted feedback…" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <span className="customer-count"><MessageSquare size={16} />{feedback ? `${filteredFeedback.length} records` : 'Feedback unavailable'}</span>
      </div>

      <div className="customer-filters">
        {sentimentFilters.map((sentiment) => <button key={sentiment} className={activeSentiment === sentiment ? 'customer-filter active' : 'customer-filter'} onClick={() => setActiveSentiment(sentiment)}>{sentiment}</button>)}
      </div>

      {loading && !feedback ? <div className="customer-empty" role="status">Loading feedback analysis…</div> : !feedback ? (
        <div className="customer-empty" role="alert"><h3>Feedback analysis unavailable</h3><p>The feedback API did not return company data.</p></div>
      ) : filteredFeedback.length ? (
        <div className="customer-feedback-list">
          {filteredFeedback.map((item) => {
            const sentiment = String(item.sentiment || 'unknown').toLowerCase();
            const SentimentIcon = sentimentIcons[sentiment] || Minus;
            return <article className="feedback-card" key={item.feedback_id || item.feedback_text}>
              <div className="feedback-card-top"><div><h3>{item.product_name || 'Customer-submitted feedback'}</h3><span className="feedback-category">{(item.topics || ['general']).join(', ')}</span></div>
                <span className={`feedback-sentiment ${sentiment}`}><SentimentIcon size={14} />{sentiment}</span></div>
              <p>{item.feedback_text || 'Feedback text unavailable.'}</p>
              <div className="feedback-card-bottom"><span>{item.rating == null ? 'Rating unavailable' : `Rating ${item.rating}/5`}</span><button type="button" onClick={() => setSelectedFeedback(item)}>View details</button></div>
            </article>;
          })}
        </div>
      ) : <div className="customer-empty"><Search size={25} /><h3>{records.length ? 'No feedback matches this filter' : 'No feedback records available'}</h3><p>{records.length ? 'Try another search or sentiment filter.' : 'Submit a customer record to begin analysis.'}</p></div>}

      {selectedFeedback && <div className="feedback-detail"><div className="feedback-detail-heading"><h3>Feedback Details</h3><button type="button" onClick={() => setSelectedFeedback(null)}>Close</button></div>
        <p><strong>Topics:</strong> {(selectedFeedback.topics || ['general']).join(', ')}</p><p><strong>Sentiment:</strong> {selectedFeedback.sentiment || 'unknown'}</p><p><strong>Rating:</strong> {selectedFeedback.rating ?? 'Unavailable'}</p><p><strong>Feedback:</strong> {selectedFeedback.feedback_text}</p>
        {selectedFeedback.source_url && <a href={selectedFeedback.source_url} target="_blank" rel="noreferrer">Open supplied feedback source</a>}
      </div>}
      <p className="customer-demo-notice">The current API exposes aggregated company feedback with sample evidence. It does not provide automatic public-review discovery.</p>
    </div>
  );
}
