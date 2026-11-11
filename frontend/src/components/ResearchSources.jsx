
import { useMemo, useState } from "react";
import {
  Search,
  FileText,
  Globe,
  Newspaper,
  BookOpen,
  CalendarDays,
  ExternalLink,
} from "lucide-react";

const sampleSources = [
  {
    id: 1,
    title: "Company Product Strategy and Roadmap",
    publisher: "Company Blog",
    type: "Blog",
    date: "2025-10-20",
    description:
      "An overview of the company's product direction, priorities and upcoming capabilities.",
  },
  {
    id: 2,
    title: "Annual Technology Industry Report",
    publisher: "Industry Research",
    type: "Report",
    date: "2025-09-12",
    description:
      "Research covering technology trends, market developments and competitive activity.",
  },
  {
    id: 3,
    title: "New Product Features Announced",
    publisher: "Technology News",
    type: "News",
    date: "2025-08-05",
    description:
      "A news article discussing recent product announcements and feature improvements.",
  },
  {
    id: 4,
    title: "Product Documentation and User Guide",
    publisher: "Official Documentation",
    type: "Documentation",
    date: "2025-06-18",
    description:
      "Documentation explaining product capabilities, features and usage.",
  },
  {
    id: 5,
    title: "Market Trends and Customer Expectations",
    publisher: "Market Research",
    type: "Report",
    date: "2025-04-10",
    description:
      "An overview of customer expectations and emerging trends in the market.",
  },
];

const sourceTypes = [
  "All",
  "Blog",
  "News",
  "Report",
  "Documentation",
];

const sourceIcons = {
  Blog: Globe,
  News: Newspaper,
  Report: BookOpen,
  Documentation: FileText,
};

export default function ResearchSources() {
  const [search, setSearch] = useState("");
  const [activeType, setActiveType] = useState("All");

  const filteredSources = useMemo(() => {
    return sampleSources.filter((source) => {
      const searchText = search.toLowerCase();

      const matchesSearch =
        source.title.toLowerCase().includes(searchText) ||
        source.publisher.toLowerCase().includes(searchText) ||
        source.description.toLowerCase().includes(searchText);

      const matchesType =
        activeType === "All" || source.type === activeType;

      return matchesSearch && matchesType;
    });
  }, [search, activeType]);

  return (
    <div className="sources-page">
      <div className="sources-toolbar">
        <div className="sources-search">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search research sources..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="sources-count">
          <FileText size={17} />
          {filteredSources.length} sources
        </div>
      </div>

      <div className="sources-filters">
        {sourceTypes.map((type) => (
          <button
            key={type}
            className={
              activeType === type
                ? "sources-filter active"
                : "sources-filter"
            }
            onClick={() => setActiveType(type)}
          >
            {type}
          </button>
        ))}
      </div>

      <div className="sources-list">
        {filteredSources.length > 0 ? (
          filteredSources.map((source) => {
            const SourceIcon = sourceIcons[source.type];

            return (
              <article className="source-card" key={source.id}>
                <div className="source-icon">
                  <SourceIcon size={20} />
                </div>

                <div className="source-details">
                  <div className="source-card-top">
                    <span className="source-type">
                      {source.type}
                    </span>

                    <span className="source-date">
                      <CalendarDays size={14} />
                      {new Date(source.date).toLocaleDateString(
                        "en-IN",
                        {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        }
                      )}
                    </span>
                  </div>

                  <h3>{source.title}</h3>
                  <span className="source-publisher">
                    {source.publisher}
                  </span>
                  <p>{source.description}</p>
                </div>
              </article>
            );
          })
        ) : (
          <div className="sources-empty">
            <Search size={25} />
            <h3>No sources found</h3>
            <p>Try another search or select a different source type.</p>
          </div>
        )}
      </div>

      <p className="sources-demo-notice">
        Demonstration sources only. Real research sources will be
        loaded from the NEXUS backend after integration.
      </p>
    </div>
  );
}
