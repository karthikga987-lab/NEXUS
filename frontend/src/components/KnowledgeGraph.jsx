
import { useState } from "react";
import {
  Building2,
  Package,
  Cpu,
  Users,
  GitBranch,
  Search,
} from "lucide-react";

const nodes = [
  { id: "company", label: "Company", type: "Company", x: 420, y: 220 },
  { id: "product1", label: "Product A", type: "Product", x: 190, y: 90 },
  { id: "product2", label: "Product B", type: "Product", x: 650, y: 90 },
  { id: "tech1", label: "AI Technology", type: "Technology", x: 170, y: 350 },
  { id: "tech2", label: "Cloud Platform", type: "Technology", x: 660, y: 350 },
  { id: "customer", label: "Customers", type: "Customer", x: 420, y: 450 },
  { id: "competitor", label: "Competitor", type: "Competitor", x: 420, y: 65 },
];

const relationships = [
  { from: "company", to: "product1", label: "Develops" },
  { from: "company", to: "product2", label: "Owns" },
  { from: "company", to: "tech1", label: "Uses" },
  { from: "company", to: "tech2", label: "Uses" },
  { from: "company", to: "customer", label: "Serves" },
  { from: "company", to: "competitor", label: "Competes with" },
  { from: "product1", to: "tech1", label: "Powered by" },
  { from: "product2", to: "tech2", label: "Runs on" },
];

const nodeIcons = {
  Company: Building2,
  Product: Package,
  Technology: Cpu,
  Customer: Users,
  Competitor: GitBranch,
};

const filters = [
  "All",
  "Company",
  "Product",
  "Technology",
  "Customer",
  "Competitor",
];

export default function KnowledgeGraph() {
  const [activeFilter, setActiveFilter] = useState("All");
  const [selectedNode, setSelectedNode] = useState("company");
  const [search, setSearch] = useState("");

  const filteredNodes = nodes.filter((node) => {
    const matchesFilter =
      activeFilter === "All" || node.type === activeFilter;

    const matchesSearch = node.label
      .toLowerCase()
      .includes(search.toLowerCase());

    return matchesFilter && matchesSearch;
  });

  const visibleIds = new Set(filteredNodes.map((node) => node.id));

  const selected = nodes.find((node) => node.id === selectedNode);

  const connectedRelationships = relationships.filter(
    (relationship) =>
      relationship.from === selectedNode ||
      relationship.to === selectedNode
  );

  return (
    <div className="graph-page">
      <div className="graph-toolbar">
        <div className="graph-search">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search graph entities..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>

        <span className="graph-count">
          <GitBranch size={16} />
          {filteredNodes.length} entities
        </span>
      </div>

      <div className="graph-filters">
        {filters.map((filter) => (
          <button
            key={filter}
            className={
              activeFilter === filter
                ? "graph-filter active"
                : "graph-filter"
            }
            onClick={() => setActiveFilter(filter)}
          >
            {filter}
          </button>
        ))}
      </div>

      <div className="graph-layout">
        <div className="graph-canvas">
          <svg
            viewBox="0 0 840 530"
            role="img"
            aria-label="Demonstration company knowledge graph"
          >
            {relationships.map((relationship, index) => {
              const from = nodes.find(
                (node) => node.id === relationship.from
              );
              const to = nodes.find(
                (node) => node.id === relationship.to
              );

              if (
                !visibleIds.has(from.id) ||
                !visibleIds.has(to.id)
              ) {
                return null;
              }

              return (
                <g key={index}>
                  <line
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke="#8b5cf6"
                    strokeWidth="2"
                    opacity="0.55"
                  />
                  <text
                    x={(from.x + to.x) / 2}
                    y={(from.y + to.y) / 2 - 8}
                    fill="#aaa7c0"
                    fontSize="11"
                    textAnchor="middle"
                  >
                    {relationship.label}
                  </text>
                </g>
              );
            })}

            {filteredNodes.map((node) => {
              const Icon = nodeIcons[node.type];
              const isSelected = selectedNode === node.id;

              return (
                <g
                  key={node.id}
                  onClick={() => setSelectedNode(node.id)}
                  style={{ cursor: "pointer" }}
                >
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={isSelected ? 43 : 35}
                    fill={
                      isSelected
                        ? "rgba(139,92,246,0.35)"
                        : "rgba(139,92,246,0.14)"
                    }
                    stroke={isSelected ? "#c4b5fd" : "#8b5cf6"}
                    strokeWidth={isSelected ? 3 : 1.5}
                  />
                  <text
                    x={node.x}
                    y={node.y + 5}
                    textAnchor="middle"
                    fill="#f5f3ff"
                    fontSize="12"
                    fontWeight="600"
                  >
                    {node.label.length > 13
                      ? node.label.slice(0, 12) + "…"
                      : node.label}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        <aside className="graph-details">
          <h3>Entity Details</h3>

          {selected && visibleIds.has(selected.id) ? (
            <>
              <span className="graph-detail-type">{selected.type}</span>
              <h2>{selected.label}</h2>
              <p>
                This is a demonstration entity in the NEXUS
                knowledge graph.
              </p>

              <h4>Connected relationships</h4>

              {connectedRelationships.length > 0 ? (
                connectedRelationships.map((relationship, index) => {
                  const otherId =
                    relationship.from === selectedNode
                      ? relationship.to
                      : relationship.from;

                  const otherNode = nodes.find(
                    (node) => node.id === otherId
                  );

                  return (
                    <div className="graph-relationship" key={index}>
                      <span>{relationship.label}</span>
                      <strong>{otherNode.label}</strong>
                    </div>
                  );
                })
              ) : (
                <p>No connected relationships.</p>
              )}
            </>
          ) : (
            <p>Select a visible entity to view its details.</p>
          )}
        </aside>
      </div>

      <p className="graph-demo-notice">
        Demonstration knowledge graph only. Real entities and
        relationships will be loaded from the NEXUS backend
        after integration.
      </p>
    </div>
  );
}
