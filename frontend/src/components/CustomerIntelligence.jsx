
import { useMemo, useState } from "react";
import {
  Search,
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
  Minus,
  TrendingUp,
} from "lucide-react";

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

const sentimentIcons = {
  Positive: ThumbsUp,
  Negative: ThumbsDown,
  Neutral: Minus,
};

const sentimentFilters = ["All", "Positive", "Negative", "Neutral"];

export default function CustomerIntelligence() {
  const [search, setSearch] = useState("");
  const [activeSentiment, setActiveSentiment] = useState("All");
  const [selectedFeedback, setSelectedFeedback] = useState(null);

  const filteredFeedback = useMemo(() => {
    return sampleFeedback.filter((item) => {
      const searchText = search.toLowerCase();

      const matchesSearch =
        item.customer.toLowerCase().includes(searchText) ||
        item.category.toLowerCase().includes(searchText) ||
        item.message.toLowerCase().includes(searchText);

      const matchesSentiment =
        activeSentiment === "All" ||
        item.sentiment === activeSentiment;

      return matchesSearch && matchesSentiment;
    });
  }, [search, activeSentiment]);

  const positiveCount = sampleFeedback.filter(
    (item) => item.sentiment === "Positive"
  ).length;

  const negativeCount = sampleFeedback.filter(
    (item) => item.sentiment === "Negative"
  ).length;

  const neutralCount = sampleFeedback.filter(
    (item) => item.sentiment === "Neutral"
  ).length;

  return (
    <div className="customer-page">
      <div className="customer-stats">
        <div className="customer-stat-card">
          <span>Total Feedback</span>
          <h2>{sampleFeedback.length}</h2>
          <p>Demonstration entries</p>
        </div>

        <div className="customer-stat-card">
          <span>Positive</span>
          <h2>{positiveCount}</h2>
          <p>Positive feedback entries</p>
        </div>

        <div className="customer-stat-card">
          <span>Negative</span>
          <h2>{negativeCount}</h2>
          <p>Negative feedback entries</p>
        </div>

        <div className="customer-stat-card">
          <span>Neutral</span>
          <h2>{neutralCount}</h2>
          <p>Neutral feedback entries</p>
        </div>
      </div>

      <div className="customer-toolbar">
        <div className="customer-search">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search customer feedback..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        <span className="customer-count">
          <MessageSquare size={16} />
          {filteredFeedback.length} entries
        </span>
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
            const SentimentIcon = sentimentIcons[item.sentiment];

            return (
              <article className="feedback-card" key={item.id}>
                <div className="feedback-card-top">
                  <div>
                    <h3>{item.customer}</h3>
                    <span className="feedback-category">
                      {item.category}
                    </span>
                  </div>

                  <span
                    className={`feedback-sentiment ${item.sentiment.toLowerCase()}`}
                  >
                    <SentimentIcon size={14} />
                    {item.sentiment}
                  </span>
                </div>

                <p>{item.message}</p>

                <div className="feedback-card-bottom">
                  <span>{item.date}</span>
                  <button
                    onClick={() => setSelectedFeedback(item)}
                  >
                    View details
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

      {selectedFeedback && (
        <div className="feedback-detail">
          <div className="feedback-detail-heading">
            <h3>Feedback Details</h3>
            <button onClick={() => setSelectedFeedback(null)}>
              Close
            </button>
          </div>

          <p><strong>Customer:</strong> {selectedFeedback.customer}</p>
          <p><strong>Category:</strong> {selectedFeedback.category}</p>
          <p><strong>Sentiment:</strong> {selectedFeedback.sentiment}</p>
          <p><strong>Date:</strong> {selectedFeedback.date}</p>
          <p><strong>Feedback:</strong> {selectedFeedback.message}</p>
        </div>
      )}

      <p className="customer-demo-notice">
        Demonstration customer feedback only. Real feedback and
        sentiment analysis will be loaded from the NEXUS backend
        after integration.
      </p>
    </div>
  );
}
