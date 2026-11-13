import { useMemo, useState } from 'react';
import { CalendarDays, MessageSquare, Minus, Search, Tag, ThumbsDown, ThumbsUp, TrendingUp } from 'lucide-react';
import './CustomerIntelligence.css';

const sentimentIcons = { positive: ThumbsUp, negative: ThumbsDown, neutral: Minus, mixed: Minus, unknown: Minus };
const sentimentFilters = ['All', 'Positive', 'Negative', 'Neutral', 'Mixed', 'Unknown'];
const sentimentColors = { positive: '#a78bfa', neutral: '#77718d', negative: '#d47b9c', mixed: '#e5b86a', unknown: '#545064' };

function formatDate(value) {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function CustomerIntelligence({ companyId, feedback, feedbackRecords = null, analysis, loading = false, onSubmitFeedback }) {
  const [search, setSearch] = useState('');
  const [activeSentiment, setActiveSentiment] = useState('All');
  const [selectedFeedback, setSelectedFeedback] = useState(null);
  const [text, setText] = useState('');
  const [productName, setProductName] = useState('');
  const [rating, setRating] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formMessage, setFormMessage] = useState('');

  const records = useMemo(() => {
    if (Array.isArray(feedbackRecords)) {
      return feedbackRecords.map((item) => ({
        ...item,
        feedback_id: item.feedback_id || item.id,
        topics: Array.isArray(item.topics) ? item.topics : [],
      }));
    }
    const byId = new Map();
    (feedback?.trends || []).forEach((trend) => (trend.evidence || []).forEach((item) => {
      const id = item.feedback_id || `${trend.topic}:${item.feedback_text}`;
      const existing = byId.get(id);
      if (existing) existing.topics = [...new Set([...existing.topics, trend.topic])];
      else byId.set(id, { ...item, topics: [trend.topic] });
    }));
    return [...byId.values()];
  }, [feedback, feedbackRecords]);

  const filteredFeedback = useMemo(() => records.filter((item) => {
    const sentiment = String(item.sentiment || 'unknown').toLowerCase();
    const searchable = `${item.feedback_text || ''} ${item.product_name || ''} ${(item.topics || []).join(' ')}`.toLowerCase();
    return (activeSentiment === 'All' || sentiment === activeSentiment.toLowerCase()) && searchable.includes(search.toLowerCase());
  }), [records, search, activeSentiment]);

  const distribution = analysis?.sentiment_distribution || {};
  const countFor = (kind) => Number(distribution[kind] ?? records.filter((item) => String(item.sentiment || 'unknown').toLowerCase() === kind).length);
  const positiveCount = countFor('positive');
  const negativeCount = countFor('negative');
  const neutralCount = countFor('neutral');
  const mixedCount = countFor('mixed');
  const unknownCount = countFor('unknown');
  const classifiedCount = positiveCount + negativeCount + neutralCount + mixedCount + unknownCount;
  const topicItems = (feedback?.trends || []).map((trend) => ({ name: trend.topic || 'Unclassified', count: Number(trend.total_feedback || 0) }));
  const highestTopicCount = Math.max(1, ...topicItems.map((topic) => topic.count));
  const hasFeedbackData = feedback != null || Array.isArray(feedbackRecords);
  const totalFeedback = Array.isArray(feedbackRecords)
    ? feedbackRecords.length
    : feedback?.total_feedback;
  const percentages = classifiedCount ? {
    positive: Math.round((positiveCount / classifiedCount) * 100),
    neutral: Math.round((neutralCount / classifiedCount) * 100),
    negative: Math.round((negativeCount / classifiedCount) * 100),
  } : { positive: 0, neutral: 0, negative: 0 };
  const positiveEnd = percentages.positive;
  const neutralEnd = positiveEnd + percentages.neutral;

  async function submit(event) {
    event.preventDefault();
    if (!text.trim()) return;
    setSubmitting(true);
    setFormMessage('');
    try {
      await onSubmitFeedback({ company_id: companyId, text: text.trim(), product_name: productName.trim() || null, rating: rating === '' ? null : Number(rating) });
      setText(''); setProductName(''); setRating('');
      setFormMessage('Feedback saved. Its topic and sentiment labels are heuristic.');
    } catch (error) {
      setFormMessage(`Feedback was not saved: ${error.message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="customer-page">
      <div className="customer-heading">
        <div><span className="customer-eyebrow">CUSTOMER INTELLIGENCE</span><h2>Submitted feedback</h2><p>Company-provided records and heuristic classifications; public review discovery is not enabled.</p></div>
        <div className="customer-live-label"><span />{hasFeedbackData ? 'Company API data' : loading ? 'Loading' : 'Data unavailable'}</div>
      </div>

      <div className="customer-stats">
        {[
          ['Total feedback', totalFeedback ?? '—', 'Company records', MessageSquare],
          ['Positive', hasFeedbackData ? positiveCount : '—', 'Heuristic label', ThumbsUp],
          ['Negative', hasFeedbackData ? negativeCount : '—', 'Heuristic label', ThumbsDown],
          ['Neutral', hasFeedbackData ? neutralCount : '—', 'Heuristic label', Minus],
        ].map(([label, value, note, Icon]) => <div className="customer-stat-card" key={label}><div className="customer-stat-top"><span>{label}</span><Icon size={17} /></div><h2>{value}</h2><p>{note}</p></div>)}
      </div>

      <div className="customer-analytics-grid">
        <section className="customer-panel sentiment-panel">
          <div className="customer-section-heading"><div><h3>Sentiment overview</h3><p>API classifications are heuristic, not evidence of product outcomes.</p></div><TrendingUp size={19} /></div>
          {classifiedCount ? <div className="sentiment-content">
            <div className="sentiment-donut" style={{ background: `conic-gradient(${sentimentColors.positive} 0 ${positiveEnd}%, ${sentimentColors.neutral} ${positiveEnd}% ${neutralEnd}%, ${sentimentColors.negative} ${neutralEnd}% ${neutralEnd + percentages.negative}%, ${sentimentColors.mixed} ${neutralEnd + percentages.negative}% ${Math.min(100, neutralEnd + percentages.negative + Math.round((mixedCount / classifiedCount) * 100))}%, ${sentimentColors.unknown} ${Math.min(100, neutralEnd + percentages.negative + Math.round((mixedCount / classifiedCount) * 100))}% 100%)` }}>
              <div className="sentiment-donut-inner"><strong>{classifiedCount}</strong><span>Classified</span></div>
            </div>
            <div className="sentiment-legend">{[['positive', positiveCount], ['neutral', neutralCount], ['negative', negativeCount], ['mixed', mixedCount], ['unknown', unknownCount]].map(([kind, count]) => <div key={kind}><span className={`legend-dot ${kind}-dot`} /><span>{kind}</span><strong>{count}</strong></div>)}</div>
          </div> : <div className="customer-empty"><h3>No classified feedback</h3><p>Submit or import feedback to see available classifications.</p></div>}
        </section>

        <section className="customer-panel topics-panel">
          <div className="customer-section-heading"><div><h3>Feedback topics</h3><p>Topics returned by the feedback analysis API.</p></div><Tag size={19} /></div>
          {topicItems.length ? <div className="topic-list">{topicItems.map((topic) => <div className="topic-item" key={topic.name}><div className="topic-label"><span>{topic.name}</span><strong>{topic.count}</strong></div><div className="topic-track"><div className="topic-fill" style={{ width: `${Math.max(2, (topic.count / highestTopicCount) * 100)}%` }} /></div></div>)}</div> : <div className="customer-empty"><h3>No topic data available</h3><p>The API returned no categorized feedback topics.</p></div>}
        </section>
      </div>

      <section className="feedback-submit-panel">
        <div className="detail-section-title"><TrendingUp size={18} /><h3>Submit customer feedback</h3></div>
        <form onSubmit={submit}>
          <label>Feedback text<textarea value={text} onChange={(event) => setText(event.target.value)} maxLength={10000} required rows={3} /></label>
          <div className="feedback-submit-fields"><label>Product (optional)<input value={productName} onChange={(event) => setProductName(event.target.value)} maxLength={255} /></label><label>Rating (optional)<input type="number" min="0" max="5" step="0.5" value={rating} onChange={(event) => setRating(event.target.value)} /></label></div>
          <button type="submit" disabled={submitting || !text.trim()}>{submitting ? 'Saving…' : 'Save feedback'}</button>
          {formMessage && <p role="status">{formMessage}</p>}
        </form>
        <small>Feedback is user supplied. Topic and sentiment labels are heuristic and are not documentary proof of product events or outcomes.</small>
      </section>

      <section className="customer-panel feedback-explorer">
        <div className="customer-section-heading explorer-heading"><div><h3>Feedback explorer</h3><p>Search and inspect company-scoped submitted feedback records.</p></div><span className="feedback-total">{hasFeedbackData ? `${filteredFeedback.length} records` : 'Unavailable'}</span></div>
        <div className="customer-toolbar"><div className="customer-search"><Search size={17} /><input type="search" aria-label="Search feedback" placeholder="Search product, topic or feedback…" value={search} onChange={(event) => setSearch(event.target.value)} /></div></div>
        <div className="customer-filters">{sentimentFilters.map((sentiment) => <button type="button" key={sentiment} className={activeSentiment === sentiment ? 'customer-filter active' : 'customer-filter'} onClick={() => setActiveSentiment(sentiment)}>{sentiment}</button>)}</div>
        {loading && !hasFeedbackData ? <div className="customer-empty" role="status">Loading feedback analysis…</div> : !hasFeedbackData ? <div className="customer-empty" role="alert"><h3>Feedback unavailable</h3><p>The feedback API did not return company data.</p></div> : filteredFeedback.length ? <div className="customer-feedback-list">{filteredFeedback.map((item) => {
          const sentiment = String(item.sentiment || 'unknown').toLowerCase();
          const SentimentIcon = sentimentIcons[sentiment] || Minus;
          return <article className="feedback-card" key={item.feedback_id || item.feedback_text}>
            <div className="feedback-card-top"><div className="feedback-customer-info"><div className="feedback-avatar">{String(item.product_name || 'F').slice(0, 1).toUpperCase()}</div><div><h4>{item.product_name || 'Submitted feedback'}</h4><span className="feedback-category">{(item.topics || ['general']).join(', ')}</span></div></div><span className={`feedback-sentiment ${sentiment}`}><SentimentIcon size={14} />{sentiment}</span></div>
            <p className="feedback-message">{item.feedback_text || 'Feedback text unavailable.'}</p>
            <div className="feedback-card-bottom"><span><CalendarDays size={14} />{formatDate(item.created_at_source || item.collected_at)}</span><span>Rating {item.rating == null ? 'unavailable' : `${item.rating}/5`}</span><button type="button" onClick={() => setSelectedFeedback(item)}>View details</button></div>
          </article>;
        })}</div> : <div className="customer-empty"><Search size={25} /><h3>{records.length ? 'No feedback matches this filter' : 'No feedback records available'}</h3><p>{records.length ? 'Try another search or sentiment filter.' : 'Submit a customer record to begin analysis.'}</p></div>}
      </section>

      <div className="customer-demo-notice"><TrendingUp size={15} />Classification is heuristic; the project does not automatically discover public customer reviews.</div>

      {selectedFeedback && <div className="feedback-modal-overlay" role="presentation" onClick={() => setSelectedFeedback(null)}><div className="feedback-modal" role="dialog" aria-modal="true" aria-labelledby="feedback-dialog-title" onClick={(event) => event.stopPropagation()}>
        <div className="feedback-modal-heading"><div><span className="customer-eyebrow">FEEDBACK DETAILS</span><h3 id="feedback-dialog-title">{selectedFeedback.product_name || 'Submitted feedback'}</h3></div><button type="button" className="feedback-close" onClick={() => setSelectedFeedback(null)} aria-label="Close feedback details">×</button></div>
        <div className="feedback-modal-meta"><span>{(selectedFeedback.topics || ['general']).join(', ')}</span><span className={`feedback-sentiment ${String(selectedFeedback.sentiment || 'unknown').toLowerCase()}`}>{selectedFeedback.sentiment || 'unknown'}</span></div>
        <div className="feedback-modal-message"><span>Submitted feedback</span><p>{selectedFeedback.feedback_text || 'Unavailable'}</p></div>
        <div className="feedback-modal-date"><CalendarDays size={15} />Source date {formatDate(selectedFeedback.created_at_source)} · Collected {formatDate(selectedFeedback.collected_at)}</div>
        <div className="feedback-modal-date">Rating {selectedFeedback.rating == null ? 'unavailable' : `${selectedFeedback.rating}/5`} · {selectedFeedback.feedback_type || 'Type unavailable'} · {selectedFeedback.language || 'Language unavailable'}</div>
        {selectedFeedback.source_url && <a href={selectedFeedback.source_url} target="_blank" rel="noreferrer">Open supplied source</a>}
        <button type="button" className="feedback-modal-done" onClick={() => setSelectedFeedback(null)}>Close details</button>
      </div></div>}
    </div>
  );
}
