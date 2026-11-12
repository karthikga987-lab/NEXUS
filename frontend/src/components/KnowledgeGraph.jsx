

import { useMemo, useState } from "react";
import "./KnowledgeGraph.css";

import {
  Search,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Network,
  Building2,
  Package,
  Layers,
  Users,
  FileText,
  Sparkles,
  X,
  Move,
  MousePointer2,
} from "lucide-react";

// Illustrative data only.
// Replace these entities and relationships with validated backend data
// when the NEXUS knowledge graph API is integrated.

const initialNodes = [
  {
    id: "company",
    label: "NEXUS Company",
    type: "Company",
    description:
      "The central organization connecting products, market activity and research intelligence.",
    x: 420,
    y: 250,
    size: 27,
  },
  {
    id: "product",
    label: "Core Product",
    type: "Product",
    description:
      "A product connected to the company's strategy and feature development.",
    x: 230,
    y: 125,
    size: 21,
  },
  {
    id: "platform",
    label: "Digital Platform",
    type: "Product",
    description:
      "A platform representing the company's digital product ecosystem.",
    x: 640,
    y: 130,
    size: 21,
  },
  {
    id: "feature",
    label: "AI Features",
    type: "Feature",
    description:
      "An example feature group associated with the core product.",
    x: 100,
    y: 285,
    size: 17,
  },
  {
    id: "analytics",
    label: "Analytics",
    type: "Feature",
    description:
      "An example capability for understanding product usage and performance.",
    x: 320,
    y: 420,
    size: 17,
  },
  {
    id: "competitor",
    label: "Competitor A",
    type: "Competitor",
    description:
      "An illustrative competitor entity used to demonstrate market relationships.",
    x: 730,
    y: 330,
    size: 20,
  },
  {
    id: "research",
    label: "Market Research",
    type: "Source",
    description:
      "An example research source that may support market and product intelligence.",
    x: 540,
    y: 465,
    size: 17,
  },
  {
    id: "customers",
    label: "Customers",
    type: "Customer",
    description:
      "An example customer group connected to product adoption and feedback.",
    x: 820,
    y: 90,
    size: 19,
  },
  {
    id: "launch",
    label: "Product Launch",
    type: "Event",
    description:
      "An illustrative product event connected to the product ecosystem.",
    x: 110,
    y: 75,
    size: 16,
  },
];

const initialEdges = [
  { source: "company", target: "product", label: "owns" },
  { source: "company", target: "platform", label: "develops" },
  { source: "product", target: "feature", label: "includes" },
  { source: "product", target: "analytics", label: "includes" },
  { source: "company", target: "competitor", label: "competes with" },
  { source: "company", target: "research", label: "researched by" },
  { source: "platform", target: "customers", label: "serves" },
  { source: "product", target: "launch", label: "introduced at" },
  { source: "analytics", target: "research", label: "informed by" },
  { source: "platform", target: "competitor", label: "market overlap" },
];

const filters = [
  "All",
  "Company",
  "Product",
  "Feature",
  "Competitor",
  "Customer",
  "Source",
  "Event",
];

const nodeColors = {
  Company: "#c4b5fd",
  Product: "#a78bfa",
  Feature: "#8b9cff",
  Competitor: "#f0abfc",
  Customer: "#67e8d0",
  Source: "#fbbf75",
  Event: "#93c5fd",
};

const nodeIcons = {
  Company: Building2,
  Product: Package,
  Feature: Layers,
  Competitor: Network,
  Customer: Users,
  Source: FileText,
  Event: Sparkles,
};

export default function KnowledgeGraph() {
  const [nodes, setNodes] = useState(initialNodes);
  const [selectedId, setSelectedId] = useState("company");
  const [activeFilter, setActiveFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [zoom, setZoom] = useState(1);
  const [draggingId, setDraggingId] = useState(null);

  const selectedNode = nodes.find((node) => node.id === selectedId);

  const visibleNodes = useMemo(() => {
    return nodes.filter(
      (node) =>
        activeFilter === "All" || node.type === activeFilter
    );
  }, [nodes, activeFilter]);

  const visibleIds = useMemo(
    () => new Set(visibleNodes.map((node) => node.id)),
    [visibleNodes]
  );

  const visibleEdges = useMemo(
    () =>
      initialEdges.filter(
        (edge) =>
          visibleIds.has(edge.source) &&
          visibleIds.has(edge.target)
      ),
    [visibleIds]
  );

  const connectedIds = useMemo(() => {
    const connected = new Set();

    if (!selectedId) return connected;

    connected.add(selectedId);

    initialEdges.forEach((edge) => {
      if (edge.source === selectedId) connected.add(edge.target);
      if (edge.target === selectedId) connected.add(edge.source);
    });

    return connected;
  }, [selectedId]);

  const searchMatches = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) return new Set();

    return new Set(
      nodes
        .filter(
          (node) =>
            node.label.toLowerCase().includes(query) ||
            node.type.toLowerCase().includes(query) ||
            node.description.toLowerCase().includes(query)
        )
        .map((node) => node.id)
    );
  }, [nodes, search]);

  const selectedConnections = useMemo(() => {
    if (!selectedId) return [];

    return initialEdges
      .filter(
        (edge) =>
          edge.source === selectedId || edge.target === selectedId
      )
      .map((edge) => {
        const otherId =
          edge.source === selectedId ? edge.target : edge.source;

        const otherNode = nodes.find((node) => node.id === otherId);

        return {
          ...edge,
          otherNode,
          direction:
            edge.source === selectedId ? "outgoing" : "incoming",
        };
      })
      .filter((item) => item.otherNode);
  }, [nodes, selectedId]);

  const getNode = (id) => nodes.find((node) => node.id === id);

  const getSvgCoordinates = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();

    const viewWidth = 900 / zoom;
    const viewHeight = 560 / zoom;
    const viewX = (900 - viewWidth) / 2;
    const viewY = (560 - viewHeight) / 2;

    return {
      x:
        ((event.clientX - rect.left) / rect.width) * viewWidth +
        viewX,
      y:
        ((event.clientY - rect.top) / rect.height) * viewHeight +
        viewY,
    };
  };

  const handleNodePointerDown = (event, node) => {
    event.preventDefault();
    event.stopPropagation();

    event.currentTarget.ownerSVGElement?.setPointerCapture?.(
      event.pointerId
    );

    setSelectedId(node.id);
    setDraggingId(node.id);
  };

  const handlePointerMove = (event) => {
    if (!draggingId) return;

    const point = getSvgCoordinates(event);

    setNodes((currentNodes) =>
      currentNodes.map((node) =>
        node.id === draggingId
          ? {
              ...node,
              x: Math.max(35, Math.min(865, point.x)),
              y: Math.max(35, Math.min(525, point.y)),
            }
          : node
      )
    );
  };

  const handlePointerUp = () => {
    setDraggingId(null);
  };

  const changeZoom = (amount) => {
    setZoom((current) =>
      Math.max(0.65, Math.min(1.65, current + amount))
    );
  };

  const resetGraph = () => {
    setNodes(initialNodes);
    setZoom(1);
    setSelectedId("company");
    setActiveFilter("All");
    setSearch("");
  };

  const handleFilterChange = (filter) => {
    setActiveFilter(filter);

    if (
      selectedNode &&
      filter !== "All" &&
      selectedNode.type !== filter
    ) {
      setSelectedId(null);
    }
  };

  return (
    <div className="knowledge-page">

      {/* Header */}

      <div className="knowledge-heading">
        <div>
          <div className="knowledge-eyebrow">
            <Network size={14} />
            CONNECTED INTELLIGENCE
          </div>

          <h2>Knowledge Graph</h2>

          <p>
            Explore how companies, products, events and research
            connect with one another.
          </p>
        </div>

        <div className="knowledge-node-total">
          <span>VISIBLE ENTITIES</span>
          <strong>{visibleNodes.length}</strong>
        </div>
      </div>

      {/* Search */}

      <div className="knowledge-toolbar">
        <div className="knowledge-search">
          <Search size={17} />

          <input
            type="text"
            placeholder="Search entities, products, features..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Search knowledge graph"
          />

          {search && (
            <button
              type="button"
              className="knowledge-clear-search"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              <X size={15} />
            </button>
          )}
        </div>

        <div className="knowledge-controls">
          <button
            type="button"
            onClick={() => changeZoom(0.15)}
            title="Zoom in"
            aria-label="Zoom in"
          >
            <ZoomIn size={17} />
          </button>

          <button
            type="button"
            onClick={() => changeZoom(-0.15)}
            title="Zoom out"
            aria-label="Zoom out"
          >
            <ZoomOut size={17} />
          </button>

          <button
            type="button"
            onClick={resetGraph}
            title="Reset graph"
            aria-label="Reset graph"
          >
            <Maximize2 size={16} />
          </button>
        </div>
      </div>

      {/* Entity filters */}

      <div className="knowledge-filters">
        {filters.map((filter) => (
          <button
            key={filter}
            type="button"
            className={
              activeFilter === filter
                ? "knowledge-filter active"
                : "knowledge-filter"
            }
            onClick={() => handleFilterChange(filter)}
          >
            {filter}
          </button>
        ))}
      </div>

      {/* Main graph and details */}

      <div className="knowledge-workspace">

        <section className="knowledge-graph-panel">

          <div className="knowledge-graph-topbar">
            <div>
              <span className="knowledge-live-dot" />
              <span>ENTITY RELATIONSHIP MAP</span>
            </div>

            <span className="knowledge-graph-hint">
              <Move size={13} />
              Drag nodes to rearrange
            </span>
          </div>

          <div className="knowledge-svg-wrap">
            <svg
              className="knowledge-svg"
              viewBox={`${
                (900 - 900 / zoom) / 2
              } ${
                (560 - 560 / zoom) / 2
              } ${900 / zoom} ${560 / zoom}`}
              role="img"
              aria-label="Interactive knowledge graph showing connected entities"
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
            >
              <defs>
                <pattern
                  id="knowledge-grid"
                  width="32"
                  height="32"
                  patternUnits="userSpaceOnUse"
                >
                  <circle
                    cx="1"
                    cy="1"
                    r="1"
                    fill="#a78bfa"
                    opacity="0.16"
                  />
                </pattern>

                <filter
                  id="knowledge-glow"
                  x="-100%"
                  y="-100%"
                  width="300%"
                  height="300%"
                >
                  <feGaussianBlur stdDeviation="5" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              <rect
                x="-1000"
                y="-1000"
                width="3000"
                height="3000"
                fill="url(#knowledge-grid)"
              />

              {/* Relationship lines */}

              {visibleEdges.map((edge, index) => {
                const source = getNode(edge.source);
                const target = getNode(edge.target);

                if (!source || !target) return null;

                const isConnected =
                  selectedId === edge.source ||
                  selectedId === edge.target;

                const isSearchMatch =
                  searchMatches.has(edge.source) ||
                  searchMatches.has(edge.target);

                const isDimmed =
                  (selectedId && !isConnected) ||
                  (search && !isSearchMatch);

                const midX = (source.x + target.x) / 2;
                const midY = (source.y + target.y) / 2;

                return (
                  <g key={`${edge.source}-${edge.target}`}>
                    <line
                      x1={source.x}
                      y1={source.y}
                      x2={target.x}
                      y2={target.y}
                      className={
                        isConnected
                          ? "knowledge-edge selected"
                          : "knowledge-edge"
                      }
                      opacity={isDimmed ? 0.1 : 1}
                    />

                    <text
                      x={midX}
                      y={midY - 8}
                      className="knowledge-edge-label"
                      opacity={isDimmed ? 0.08 : 0.85}
                    >
                      {edge.label}
                    </text>
                  </g>
                );
              })}

              {/* Entity nodes */}

              {visibleNodes.map((node) => {
                const isSelected = selectedId === node.id;
                const isConnected = connectedIds.has(node.id);
                const isSearchMatch = searchMatches.has(node.id);

                const isDimmed =
                  (selectedId && !isConnected) ||
                  (search && !isSearchMatch);

                return (
                  <g
                    key={node.id}
                    className={`knowledge-node ${
                      isSelected ? "selected" : ""
                    } ${draggingId === node.id ? "dragging" : ""}`}
                    transform={`translate(${node.x}, ${node.y})`}
                    onPointerDown={(event) =>
                      handleNodePointerDown(event, node)
                    }
                    onClick={() => setSelectedId(node.id)}
                    opacity={isDimmed ? 0.22 : 1}
                    style={{
                      "--node-color": nodeColors[node.type],
                    }}
                  >
                    {isSelected && (
                      <circle
                        r={node.size + 13}
                        className="knowledge-node-halo"
                      />
                    )}

                    {isSearchMatch && search && (
                      <circle
                        r={node.size + 10}
                        className="knowledge-search-halo"
                      />
                    )}

                    <circle
                      r={node.size + 5}
                      className="knowledge-node-ring"
                    />

                    <circle
                      r={node.size}
                      className="knowledge-node-core"
                    />

                    <circle
                      r="3"
                      className="knowledge-node-center"
                    />

                    <text
                      y={node.size + 23}
                      className="knowledge-node-label"
                    >
                      {node.label}
                    </text>

                    <text
                      y={node.size + 38}
                      className="knowledge-node-type"
                    >
                      {node.type.toUpperCase()}
                    </text>
                  </g>
                );
              })}
            </svg>

            {visibleNodes.length === 0 && (
              <div className="knowledge-no-nodes">
                <Search size={25} />
                <h3>No entities in this filter</h3>
                <p>Choose another entity type to explore the graph.</p>
              </div>
            )}
          </div>

          {/* Graph legend */}

          <div className="knowledge-legend">
            {Object.entries(nodeColors).map(([type, color]) => (
              <div className="knowledge-legend-item" key={type}>
                <span style={{ background: color }} />
                {type}
              </div>
            ))}
          </div>

        </section>

        {/* Selected entity panel */}

        <aside className="knowledge-details">

          <div className="knowledge-details-heading">
            <div>
              <span>ENTITY INSPECTOR</span>
              <h3>Node Details</h3>
            </div>

            <Network size={19} />
          </div>

          {selectedNode ? (
            <>
              <div className="knowledge-selected-icon">
                {(() => {
                  const SelectedIcon = nodeIcons[selectedNode.type];
                  return <SelectedIcon size={25} />;
                })()}
              </div>

              <span className="knowledge-selected-type">
                {selectedNode.type}
              </span>

              <h2 className="knowledge-selected-title">
                {selectedNode.label}
              </h2>

              <p className="knowledge-selected-description">
                {selectedNode.description}
              </p>

              <div className="knowledge-detail-divider" />

              <div className="knowledge-connection-heading">
                <span>DIRECT CONNECTIONS</span>
                <strong>{selectedConnections.length}</strong>
              </div>

              <div className="knowledge-connection-list">
                {selectedConnections.length > 0 ? (
                  selectedConnections.map((connection, index) => {
                    const ConnectedIcon =
                      nodeIcons[connection.otherNode.type];

                    return (
                      <button
                        type="button"
                        className="knowledge-connection"
                        key={`${connection.otherNode.id}-${index}`}
                        onClick={() =>
                          setSelectedId(connection.otherNode.id)
                        }
                      >
                        <div className="knowledge-connection-icon">
                          <ConnectedIcon size={16} />
                        </div>

                        <div className="knowledge-connection-text">
                          <strong>
                            {connection.otherNode.label}
                          </strong>

                          <span>
                            {connection.direction === "outgoing"
                              ? connection.label
                              : `connected via ${connection.label}`}
                          </span>
                        </div>

                        <span className="knowledge-connection-arrow">
                          →
                        </span>
                      </button>
                    );
                  })
                ) : (
                  <p className="knowledge-no-connections">
                    No direct connections in this graph view.
                  </p>
                )}
              </div>

              <button
                type="button"
                className="knowledge-focus-button"
                onClick={() => {
                  setActiveFilter("All");
                  setSearch("");
                  setNodes(initialNodes);
                  setZoom(1);
                  setSelectedId(selectedNode.id);
                }}
              >
                <MousePointer2 size={15} />
                Focus this entity
              </button>
            </>
          ) : (
            <div className="knowledge-unselected">
              <Network size={30} />
              <h3>Select an entity</h3>
              <p>
                Click any node in the graph to inspect its details
                and relationships.
              </p>
            </div>
          )}

        </aside>
      </div>

      {/* Demo notice */}

      <div className="knowledge-demo-notice">
        <Sparkles size={14} />
        Interactive demonstration graph. Replace illustrative entities
        and relationships with validated NEXUS backend data during integration.
      </div>

    </div>
  );
}
