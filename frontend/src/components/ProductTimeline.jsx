import { useMemo, useState } from "react";
import {
  CalendarDays,
  Search,
  Rocket,
  FlaskConical,
  Layers,
  RefreshCw,
  Building2,
} from "lucide-react";

const categoryIcons = {
  Launch: Rocket,
  Feature: Layers,
  Experiment: FlaskConical,
  Update: RefreshCw,
  Acquisition: Building2,
};

function formatDate(value) {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

function iconForType(value) {
  const type = String(value || '').toLowerCase();
  if (type.includes('launch')) return categoryIcons.Launch;
  if (type.includes('experiment')) return categoryIcons.Experiment;
  if (type.includes('feature')) return categoryIcons.Feature;
  if (type.includes('update') || type.includes('change')) return categoryIcons.Update;
  return Building2;
}

export default function ProductTimeline({ events, sources = [], loading = false }) {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");
  const categories = ['All', ...new Set((events || []).map((event) => event.event_type).filter(Boolean))];

  const filteredEvents = useMemo(() => {
    return (events || []).filter((event) => {
      const text = `${event.title || ''} ${event.product_name || ''} ${event.description || ''} ${event.stated_reason || ''} ${event.reported_outcome || ''}`.toLowerCase();
      const matchesSearch = text.includes(search.toLowerCase());

      const matchesCategory =
        activeCategory === "All" ||
        event.event_type === activeCategory;

      return matchesSearch && matchesCategory;
    });
  }, [events, search, activeCategory]);

  return (
    <div className="timeline-page">

      <div className="timeline-toolbar">
        <div className="timeline-search">
          <Search size={18} />

          <input
            type="text"
            placeholder="Search product events..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="timeline-count">
          <CalendarDays size={17} />
          {events ? `${filteredEvents.length} events` : 'Events unavailable'}
        </div>
      </div>

      <div className="timeline-filters">
        {categories.map((category) => (
          <button
            key={category}
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

      <div className="timeline-list">

        {loading && !events ? (
          <div className="timeline-empty" role="status">Loading product events…</div>
        ) : events === null || events === undefined ? (
          <div className="timeline-empty" role="alert"><h3>Events could not be loaded</h3><p>Check the API connection and reload company data.</p></div>
        ) : filteredEvents.length > 0 ? (
          filteredEvents.map((event) => {
            const EventIcon = iconForType(event.event_type);
            const sourceById = new Map(sources.map((source) => [source.id, source]));

            return (
              <article className="timeline-event" key={event.id}>

                <div className="timeline-marker">
                  <EventIcon size={18} />
                </div>

                <div className="timeline-event-card">

                  <div className="timeline-event-top">
                    <span className="timeline-category">{event.event_type || 'Event type unavailable'}</span>

                    <span className="timeline-date">
                      {formatDate(event.event_date)}
                    </span>
                  </div>

                  <h3>{event.title}</h3>

                  <p>{event.description || 'Description unavailable.'}</p>
                  <div className="timeline-event-facts">
                    <span><b>Product</b> {event.product_name || 'Unavailable'}</span>
                    <span><b>Evidence</b> {event.evidence_classification || 'Unknown'}</span>
                  </div>
                  {event.stated_reason && <p><b>Stated reason:</b> {event.stated_reason}</p>}
                  {event.reported_outcome && <p><b>Reported outcome:</b> {event.reported_outcome}</p>}
                  <div className="timeline-event-sources">
                    {event.source_ids?.length ? event.source_ids.map((sourceId) => {
                      const source = sourceById.get(sourceId);
                      return source ? <a key={sourceId} href={source.original_url || source.url} target="_blank" rel="noreferrer">{source.title || source.url}</a> : <span key={sourceId}>Source reference {sourceId}</span>;
                    }) : <span>No linked source is available.</span>}
                  </div>

                </div>

              </article>
            );
          })
        ) : (
          <div className="timeline-empty">
            <Search size={25} />
            <h3>No events found</h3>
            <p>Try another search or select a different category.</p>
          </div>
        )}

      </div>

      <p className="timeline-demo-notice">Events and evidence classifications are returned by the NEXUS API. Date ordering does not imply causation.</p>

    </div>
  );
}
