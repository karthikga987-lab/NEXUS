import { useEffect, useMemo, useState } from 'react';
import { Building2, Package, Cpu, Users, GitBranch, Search, CircleDot } from 'lucide-react';

const nodeIcons = { Company: Building2, Product: Package, Technology: Cpu, Customer: Users, Competitor: GitBranch, Event: CircleDot };

function labelFor(node) {
  return node.title || node.label || node.name || node.product_name || node.source_title || node.id;
}

function typeFor(node) {
  const raw = node.node_type || node.type || node.entity_type || 'Entity';
  return String(raw).replaceAll('_', ' ');
}

function layoutNodes(nodes) {
  const centerX = 420;
  const centerY = 260;
  const radius = Math.min(205, 90 + nodes.length * 10);
  return nodes.map((node, index) => {
    if (nodes.length === 1) return { ...node, x: centerX, y: centerY };
    const angle = (2 * Math.PI * index / nodes.length) - Math.PI / 2;
    return { ...node, x: centerX + radius * Math.cos(angle), y: centerY + radius * Math.sin(angle) };
  });
}

export default function KnowledgeGraph({ graph, loading = false }) {
  const [activeFilter, setActiveFilter] = useState('All');
  const [selectedNode, setSelectedNode] = useState('');
  const [search, setSearch] = useState('');
  const nodes = useMemo(() => layoutNodes(graph?.nodes || []), [graph]);
  const edges = graph?.edges || [];
  const filters = ['All', ...new Set(nodes.map(typeFor))];

  useEffect(() => {
    if (!nodes.some((node) => node.id === selectedNode)) setSelectedNode(nodes[0]?.id || '');
  }, [nodes, selectedNode]);

  const filteredNodes = nodes.filter((node) => {
    const matchesFilter = activeFilter === 'All' || typeFor(node) === activeFilter;
    return matchesFilter && labelFor(node).toLowerCase().includes(search.toLowerCase());
  });
  const visibleIds = new Set(filteredNodes.map((node) => node.id));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const selected = nodeById.get(selectedNode);
  const connectedEdges = edges.filter((edge) => edge.source === selectedNode || edge.target === selectedNode);

  if (loading && !graph) return <div className="graph-empty" role="status">Loading evidence graph…</div>;
  if (!graph) return <div className="graph-empty" role="alert"><h3>Knowledge graph unavailable</h3><p>The graph API did not return company data.</p></div>;

  return (
    <div className="graph-page">
      <div className="graph-toolbar">
        <div className="graph-search"><Search size={18} /><input type="search" placeholder="Search graph entities…" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
        <span className="graph-count"><GitBranch size={16} />{filteredNodes.length} of {nodes.length} entities</span>
      </div>
      {filters.length > 1 && <div className="graph-filters">
        {filters.map((filter) => <button key={filter} className={activeFilter === filter ? 'graph-filter active' : 'graph-filter'} onClick={() => setActiveFilter(filter)}>{filter}</button>)}
      </div>}

      {nodes.length ? <div className="graph-layout">
        <div className="graph-canvas">
          <svg viewBox="0 0 840 530" role="img" aria-label="Company evidence graph">
            {edges.map((edge) => {
              const from = nodeById.get(edge.source);
              const to = nodeById.get(edge.target);
              if (!from || !to || !visibleIds.has(from.id) || !visibleIds.has(to.id)) return null;
              const relationship = edge.relation_type || edge.relationship_type || edge.type || 'related';
              return <g key={edge.id || `${edge.source}-${edge.target}-${relationship}`}>
                <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="#8b5cf6" strokeWidth="2" opacity="0.55" />
                <text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 8} fill="#aaa7c0" fontSize="10" textAnchor="middle">{String(relationship).slice(0, 22)}</text>
              </g>;
            })}
            {filteredNodes.map((node) => {
              const isSelected = selectedNode === node.id;
              const label = labelFor(node);
              return <g key={node.id} onClick={() => setSelectedNode(node.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelectedNode(node.id); }} role="button" tabIndex="0" aria-label={`${typeFor(node)}: ${label}`} style={{ cursor: 'pointer' }}>
                <circle cx={node.x} cy={node.y} r={isSelected ? 43 : 35} fill={isSelected ? 'rgba(139,92,246,0.35)' : 'rgba(139,92,246,0.14)'} stroke={isSelected ? '#c4b5fd' : '#8b5cf6'} strokeWidth={isSelected ? 3 : 1.5} />
                <text x={node.x} y={node.y + 5} textAnchor="middle" fill="#f5f3ff" fontSize="11" fontWeight="600">{label.length > 13 ? `${label.slice(0, 12)}…` : label}</text>
              </g>;
            })}
          </svg>
        </div>
        <aside className="graph-details">
          <h3>Entity Details</h3>
          {selected ? <>
            <span className="graph-detail-type">{typeFor(selected)}</span>
            <h2>{labelFor(selected)}</h2>
            <p>{selected.description || selected.evidence_classification || 'No additional node description is available.'}</p>
            <h4>Evidence-linked relationships</h4>
            {connectedEdges.length ? connectedEdges.map((edge) => {
              const otherId = edge.source === selectedNode ? edge.target : edge.source;
              const other = nodeById.get(otherId);
              return <div className="graph-relationship" key={edge.id || `${edge.source}-${edge.target}`}>
                <span>{edge.relation_type || edge.relationship_type || edge.type || 'Related'}</span>
                <strong>{other ? labelFor(other) : otherId}</strong>
                <small>{edge.evidence_classification || edge.evidence_status || 'Classification unavailable'}{edge.confidence == null ? '' : ` · Confidence ${Math.round(Number(edge.confidence) * 100)}%`}</small>
                {edge.evidence_quote && <blockquote>{edge.evidence_quote}</blockquote>}
                {edge.source_url && <a href={edge.source_url} target="_blank" rel="noreferrer">Open supporting source</a>}
              </div>;
            }) : <p>No stored evidence-backed relationship is available for this entity.</p>}
          </> : <p>Select an entity to view details.</p>}
        </aside>
      </div> : <div className="graph-empty"><h3>No graph entities are available</h3><p>The company has no persisted events or supported relationships yet.</p></div>}
      <p className="graph-demo-notice">Only graph nodes and relationships returned by the backend are shown. Temporal order does not establish causation.</p>
    </div>
  );
}
