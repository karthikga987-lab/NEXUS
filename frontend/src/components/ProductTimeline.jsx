
import { useMemo, useState } from "react";
import "./ProductTimeline.css";
import {
  CalendarDays,
  Search,
  Rocket,
  FlaskConical,
  Layers,
  RefreshCw,
  Building2,
  Activity,
  Tags,
} from "lucide-react";

const sampleEvents = [
  {
    id: 1,
    date: "2025-10-15",
    title: "Major Product Launch",
    category: "Launch",
    description:
      "A major product release introducing an improved user experience and new capabilities.",
  },
  {
    id: 2,
    date: "2025-08-22",
    title: "Feature Expansion",
    category: "Feature",
    description:
      "Introduction of additional product features to improve usability and customer experience.",
  },
  {
    id: 3,
    date: "2025-06-10",
    title: "Product Experiment",
    category: "Experiment",
    description:
      "An experimental feature was tested to understand user engagement and product adoption.",
  },
  {
    id: 4,
    date: "2025-03-05",
    title: "Platform Update",
    category: "Update",
    description:
      "A platform improvement focused on performance, stability and reliability.",
  },
  {
    id: 5,
    date: "2024-11-18",
    title: "Strategic Acquisition",
    category: "Acquisition",
    description:
      "A strategic acquisition intended to expand product capabilities and market reach.",
  },
];

const categories = [
  "All",
  "Launch",
  "Feature",
  "Experiment",
  "Update",
  "Acquisition",
];

const categoryIcons = {
  Launch: Rocket,
  Feature: Layers,
  Experiment: FlaskConical,
  Update: RefreshCw,
  Acquisition: Building2,
};

export default function ProductTimeline() {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");

  const filteredEvents = useMemo(() => {
    return sampleEvents.filter((event) => {
      const matchesSearch =
        event.title.toLowerCase().includes(search.toLowerCase()) ||
        event.description.toLowerCase().includes(search.toLowerCase());

      const matchesCategory =
        activeCategory === "All" ||
        event.category === activeCategory;

      return matchesSearch && matchesCategory;
    });
  }, [search, activeCategory]);

  const totalEvents = sampleEvents.length;

  const totalLaunches = sampleEvents.filter(
    (event) => event.category === "Launch"
  ).length;

  const totalCategories = new Set(
    sampleEvents.map((event) => event.category)
  ).size;

  return (
    <div className="timeline-page">

      {/* Page summary */}

      <div className="timeline-summary">
        <div className="timeline-summary-card">
          <span>
            <Activity size={14} />
            Total Events
          </span>
          <strong>{totalEvents}</strong>
        </div>

        <div className="timeline-summary-card">
          <span>
            <Rocket size={14} />
            Launches
          </span>
          <strong>{totalLaunches}</strong>
        </div>

        <div className="timeline-summary-card">
          <span>
            <Tags size={14} />
            Categories
          </span>
          <strong>{totalCategories}</strong>
        </div>
      </div>

      {/* Search toolbar */}

      <div className="timeline-toolbar">
        <div className="timeline-search">
          <Search size={18} />

          <input
            type="text"
            placeholder="Search product events..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search product events"
          />
        </div>

        <div className="timeline-count">
          <CalendarDays size={17} />
          {filteredEvents.length} events
        </div>
      </div>

      {/* Category filters */}

      <div className="timeline-filters">
        {categories.map((category) => (
          <button
            key={category}
            type="button"
            className={
              activeCategory === category
                ? "timeline-filter active"
                : "timeline-filter"
            }
            onClick={() => setActiveCategory(category)}
          >
            {category}
          </button>
        ))}
      </div>

      {/* Product event timeline */}

      <div className="timeline-list">

        {filteredEvents.length > 0 ? (
          filteredEvents.map((event) => {
            const EventIcon = categoryIcons[event.category];

            return (
              <article className="timeline-event" key={event.id}>

                <div className="timeline-marker">
                  <EventIcon size={18} />
                </div>

                <div className="timeline-event-card">

                  <div className="timeline-event-top">
                    <span className="timeline-category">
                      {event.category}
                    </span>

                    <span className="timeline-date">
                      {new Date(event.date).toLocaleDateString(
                        "en-IN",
                        {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        }
                      )}
                    </span>
                  </div>

                  <h3>{event.title}</h3>

                  <p>{event.description}</p>

                </div>

              </article>
            );
          })
        ) : (
          <div className="timeline-empty">
            <Search size={25} />
            <h3>No events found</h3>
            <p>
              Try another search or select a different category.
            </p>
          </div>
        )}

      </div>

      {/* Demo notice */}

      <p className="timeline-demo-notice">
        Demonstration events only. Real company history will be
        loaded from the NEXUS backend after integration.
      </p>

    </div>
  );
}
