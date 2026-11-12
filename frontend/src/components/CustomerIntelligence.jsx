
import { useMemo, useState } from "react";
import {
  Search,
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
  Minus,
  Users,
  TrendingUp,
  Sparkles,
  X,
  ArrowUpRight,
  Tag,
  CalendarDays,
} from "lucide-react";
import "./CustomerIntelligence.css";

const sampleFeedback = [
  {
    id: 1,
    customer: "Customer A",
    category: "Usability",
    sentiment: "Positive",
    date: "2025-10-18",
    message: "The new interface is simple and easy to navigate.",
  },
  {
    id: 2,
    customer: "Customer B",
    category: "Performance",
    sentiment: "Negative",
    date: "2025-10-12",
    message: "The application takes too long to load during peak hours.",
  },
  {
    id: 3,
    customer: "Customer C",
    category: "Features",
    sentiment: "Positive",
    date: "2025-09-28",
    message: "The latest features have improved our workflow.",
  },
  {
    id: 4,
    customer: "Customer D",
    category: "Support",
    sentiment: "Neutral",
    date: "2025-09-15",
    message: "Customer support was helpful, but response time could improve.",
  },
  {
    id: 5,
    customer: "Customer E",
    category: "Performance",
    sentiment: "Negative",
    date: "2025-08-30",
    message: "We experienced occasional delays while using the platform.",
  },
  {
    id: 6,
    customer: "Customer F",
    category: "Features",
    sentiment: "Positive",
    date: "2025-08-12",
    message: "The additional product capabilities are useful.",
  },
];

const sentimentFilters = ["All", "Positive", "Neutral", "Negative"];

const sentimentConfig = {
  Positive: {
    icon: ThumbsUp,
    className: "positive",
  },
  Neutral: {
    icon: Minus,
    className: "neutral",
  },
  Negative: {
    icon: ThumbsDown,
    className: "negative",
  },
};

export default function CustomerIntelligence() {
  const [search, setSearch] = useState("");
  const [activeSentiment, setActiveSentiment] = useState("All");
  const [selectedFeedback, setSelectedFeedback] = useState(null);

  const total = sampleFeedback.length;

  const counts = useMemo(() => {
    const positive = sampleFeedback.filter(
      (item) => item.sentiment === "Positive"
    ).length;

    const negative = sampleFeedback.filter(
      (item) => item.sentiment === "Negative"
    ).length;

    const neutral = sampleFeedback.filter(
      (item) => item.sentiment === "Neutral"
    ).length;

    return { positive, negative, neutral };
  }, []);

  const topics = useMemo(() => {
    const categories = {};

    sampleFeedback.forEach((item) => {
      categories[item.category] =
        (categories[item.category] || 0) + 1;
    });

    return Object.entries(categories)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, []);

  const filteredFeedback = useMemo(() => {
    const query = search.toLowerCase().trim();

    return sampleFeedback.filter((item) => {
      const matchesSearch =
        item.customer.toLowerCase().includes(query) ||
        item.category.toLowerCase().includes(query) ||
        item.message.toLowerCase().includes(query);

      const matchesSentiment =
        activeSentiment === "All" ||
        item.sentiment === activeSentiment;

      return matchesSearch && matchesSentiment;
    });
  }, [search, activeSentiment]);

  const positivePercent = Math.round((counts.positive / total) * 100);
  const negativePercent = Math.round((counts.negative / total) * 100);
  const neutralPercent = Math.round((counts.neutral / total) * 100);

  const openFeedback = (item) => setSelectedFeedback(item);

  return (
    <div className="customer-page">
      <div className="customer-heading">
        <div>
          <div className="customer-eyebrow">
            <Sparkles size={14} />
            CUSTOMER ANALYTICS
          </div>
          <h2>Customer Intelligence</h2>
          <p>
            Understand customer sentiment, discover recurring topics,
            and explore product feedback.
          </p>
        </div>

        <div className="customer-live-label">
          <span />
          Demo dataset
        </div>
      </div>

      {/* SUMMARY CARDS */}
      <div className="customer-stats">
        <div className="customer-stat-card">
          <div className="customer-stat-top">
            <span>Total Feedback</span>
            <MessageSquare size={18} />
          </div>
          <h2>{total}</h2>
          <p>Feedback entries analyzed</p>
        </div>

        <div className="customer-stat-card">
          <div className="customer-stat-top">
            <span>Positive Sentiment</span>
            <ThumbsUp size={18} />
          </div>
          <h2>{positivePercent}%</h2>
          <p>{counts.positive} positive entries</p>
        </div>

        <div className="customer-stat-card">
          <div className="customer-stat-top">
            <span>Negative Sentiment</span>
            <ThumbsDown size={18} />
          </div>
          <h2>{negativePercent}%</h2>
          <p>{counts.negative} negative entries</p>
        </div>

        <div className="customer-stat-card">
          <div className="customer-stat-top">
            <span>Unique Customers</span>
            <Users size={18} />
          </div>
          <h2>{new Set(sampleFeedback.map((item) => item.customer)).size}</h2>
          <p>Customers represented</p>
        </div>
      </div>

      {/* ANALYTICS */}
      <div className="customer-analytics-grid">
        <section className="customer-panel sentiment-panel">
          <div className="customer-section-heading">
            <div>
              <h3>Sentiment Overview</h3>
              <p>Distribution of analyzed customer feedback</p>
            </div>
            <TrendingUp size={19} />
          </div>

          <div className="sentiment-content">
            <div
              className="sentiment-donut"
              style={{
                background: `conic-gradient(
                  #a78bfa 0% ${positivePercent}%,
                  #77718d ${positivePercent}% ${positivePercent + neutralPercent}%,
                  #d47b9c ${positivePercent + neutralPercent}% 100%
                )`,
              }}
            >
              <div className="sentiment-donut-inner">
                <strong>{total}</strong>
                <span>Responses</span>
              </div>
            </div>

            <div className="sentiment-legend">
              <div>
                <span className="legend-dot positive-dot" />
                <span>Positive</span>
                <strong>{positivePercent}%</strong>
              </div>
              <div>
                <span className="legend-dot neutral-dot" />
                <span>Neutral</span>
                <strong>{neutralPercent}%</strong>
              </div>
              <div>
                <span className="legend-dot negative-dot" />
                <span>Negative</span>
                <strong>{negativePercent}%</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="customer-panel topics-panel">
          <div className="customer-section-heading">
            <div>
              <h3>Customer Topics</h3>
              <p>Most frequently mentioned categories</p>
            </div>
            <Tag size={19} />
          </div>

          <div className="topic-list">
            {topics.map((topic) => (
              <div className="topic-item" key={topic.name}>
                <div className="topic-label">
                  <span>{topic.name}</span>
                  <strong>{topic.count}</strong>
                </div>
                <div className="topic-track">
                  <div
                    className="topic-fill"
                    style={{
                      width: `${(topic.count / total) * 100}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* FEEDBACK EXPLORER */}
      <section className="customer-panel feedback-explorer">
        <div className="customer-section-heading explorer-heading">
          <div>
            <h3>Customer Feedback Explorer</h3>
            <p>Search and inspect individual customer responses</p>
          </div>
          <span className="feedback-total">
            {filteredFeedback.length} entries
          </span>
        </div>

        <div className="customer-toolbar">
          <div className="customer-search">
            <Search size={17} />
            <input
              type="text"
              placeholder="Search customers, topics or feedback..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>

        <div className="customer-filters">
          {sentimentFilters.map((sentiment) => (
            <button
              key={sentiment}
              className={
                activeSentiment === sentiment
                  ? "customer-filter active"
                  : "customer-filter"
              }
              onClick={() => setActiveSentiment(sentiment)}
            >
              {sentiment}
            </button>
          ))}
        </div>

        <div className="customer-feedback-list">
          {filteredFeedback.length > 0 ? (
            filteredFeedback.map((item) => {
              const config = sentimentConfig[item.sentiment];
              const SentimentIcon = config.icon;

              return (
                <article className="feedback-card" key={item.id}>
                  <div className="feedback-card-top">
                    <div className="feedback-customer-info">
                      <div className="feedback-avatar">
                        {item.customer.replace("Customer ", "")}
                      </div>
                      <div>
                        <h4>{item.customer}</h4>
                        <span className="feedback-category">
                          {item.category}
                        </span>
                      </div>
                    </div>

                    <span
                      className={`feedback-sentiment ${config.className}`}
                    >
                      <SentimentIcon size={14} />
                      {item.sentiment}
                    </span>
                  </div>

                  <p className="feedback-message">{item.message}</p>

                  <div className="feedback-card-bottom">
                    <span>
                      <CalendarDays size={14} />
                      {item.date}
                    </span>
                    <button onClick={() => openFeedback(item)}>
                      View details
                      <ArrowUpRight size={14} />
                    </button>
                  </div>
                </article>
              );
            })
          ) : (
            <div className="customer-empty">
              <Search size={25} />
              <h3>No feedback found</h3>
              <p>Try another search or sentiment filter.</p>
            </div>
          )}
        </div>
      </section>

      <div className="customer-demo-notice">
        <Sparkles size={15} />
        Demonstration data only. Live customer feedback and AI sentiment
        analysis will be connected to the NEXUS backend during integration.
      </div>

      {/* FEEDBACK DETAILS MODAL */}
      {selectedFeedback && (
        <div
          className="feedback-modal-overlay"
          onClick={() => setSelectedFeedback(null)}
        >
          <div
            className="feedback-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="feedback-modal-heading">
              <div>
                <span className="customer-eyebrow">FEEDBACK DETAILS</span>
                <h3>{selectedFeedback.customer}</h3>
              </div>
              <button
                className="feedback-close"
                onClick={() => setSelectedFeedback(null)}
                aria-label="Close feedback details"
              >
                <X size={19} />
              </button>
            </div>

            <div className="feedback-modal-meta">
              <span>{selectedFeedback.category}</span>
              <span className={`feedback-sentiment ${
                sentimentConfig[selectedFeedback.sentiment].className
              }`}>
                {selectedFeedback.sentiment}
              </span>
            </div>

            <div className="feedback-modal-message">
              <span>Customer message</span>
              <p>{selectedFeedback.message}</p>
            </div>

            <div className="feedback-modal-date">
              <CalendarDays size={15} />
              Submitted on {selectedFeedback.date}
            </div>

            <button
              className="feedback-modal-done"
              onClick={() => setSelectedFeedback(null)}
            >
              Close details
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


