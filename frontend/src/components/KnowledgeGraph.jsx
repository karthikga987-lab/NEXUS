import { useEffect, useMemo, useState } from 'react';
import { Building2, FileText, Layers, Maximize2, Network, Package, Search, Sparkles, Users, ZoomIn, ZoomOut } from 'lucide-react';
import './KnowledgeGraph.css';

const nodeColors = { Company: '#c4b5fd', Product: '#a78bfa', Feature: '#8b9cff', Competitor: '#f0abfc', Customer: '#67e8d0', Source: '#fbbf75', Event: '#93c5fd' };
const nodeIcons = { Company: Building2, Product: Package, Feature: Layers, Competitor: Network, Customer: Users, Source: FileText, Event: Sparkles };

function nodeType(node) {
  const value = String(node.node_type || node.type || node.entity_type || 'Entity').toLowerCase();
  if (value.includes('company')) return 'Company';
  if (value.includes('source') || value.includes('document')) return 'Source';
  if (value.includes('event')) return 'Event';
  if (value.includes('product')) return 'Product';
  if (value.includes('feature')) return 'Feature';
  if (value.includes('competitor')) return 'Competitor';
  if (value.includes('customer')) return 'Customer';
  return 'Entity';
}

function nodeLabel(node) {
  return String(node.title || node.name || node.product_name || node.label || node.id || 'Unnamed entity');
}

function positionNodes(rawNodes) {
  const centerX = 450;
  const centerY = 275;
  const radius = Math.max(0, Math.min(205, 75 + rawNodes.length * 10));
  return rawNodes.map((node, index) => {
    const angle = rawNodes.length <= 1 ? 0 : (2 * Math.PI * index / rawNodes.length) - Math.PI / 2;
    return { ...node, x: rawNodes.length <= 1 ? centerX : centerX + radius * Math.cos(angle), y: rawNodes.length <= 1 ? centerY : centerY + radius * Math.sin(angle), type: nodeType(node), label: nodeLabel(node), size: nodeType(node) === 'Company' ? 26 : 19 };
  });
}

function edgeLabel(edge) {
  return String(edge.relation_type || edge.relationship_type || edge.type || 'related').replaceAll('_', ' ');
}

export default function KnowledgeGraph({ graph, loading = false }) {
  const [activeFilter, setActiveFilter] = useState('All');
  const [selectedId, setSelectedId] = useState('');
  const [search, setSearch] = useState('');
  const [zoom, setZoom] = useState(1);
  const nodes = useMemo(() => positionNodes(Array.isArray(graph?.nodes) ? graph.nodes : []), [graph]);
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];
  const types = [...new Set(nodes.map((node) => node.type))];
  const filters = ['All', ...types];

  useEffect(() => {
    if (!nodes.some((node) => node.id === selectedId)) setSelectedId(nodes[0]?.id || '');
  }, [nodes, selectedId]);

  const query = search.trim().toLowerCase();
  const visibleNodes = nodes.filter((node) => {
    const text = `${node.label} ${node.type} ${node.description || ''} ${node.event_type || ''} ${node.publisher || ''}`.toLowerCase();
    return (activeFilter === 'All' || node.type === activeFilter) && (!query || text.includes(query));
  });
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const visibleEdges = edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
  const selected = nodeById.get(selectedId);
  const selectedConnections = edges.filter((edge) => edge.source === selectedId || edge.target === selectedId).map((edge) => {
    const otherId = edge.source === selectedId ? edge.target : edge.source;
    return { edge, other: nodeById.get(otherId), direction: edge.source === selectedId ? 'outgoing' : 'incoming' };
  }).filter((item) => item.other);
  const viewBox = `${(900 - 900 / zoom) / 2} ${(560 - 560 / zoom) / 2} ${900 / zoom} ${560 / zoom}`;

  if (loading && !graph) return <div className="knowledge-no-nodes" role="status">Loading persisted graph data…</div>;
  if (!graph) return <div className="knowledge-no-nodes" role="alert"><h3>Knowledge graph unavailable</h3><p>The graph API did not return company data.</p></div>;

  return (
    <div className="knowledge-page">
      <div className="knowledge-heading"><div><div className="knowledge-eyebrow"><Network size={14} />CONNECTED INTELLIGENCE</div><h2>Knowledge Graph</h2><p>Explore persisted company, product event and public source relationships.</p></div><div className="knowledge-node-total"><span>VISIBLE ENTITIES</span><strong>{visibleNodes.length}</strong></div></div>
      <div className="knowledge-toolbar"><div className="knowledge-search"><Search size={17} /><input type="search" placeholder="Search persisted entities…" value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search knowledge graph" /></div><div className="knowledge-controls"><button type="button" onClick={() => setZoom((value) => Math.min(1.6, value + 0.15))} title="Zoom in" aria-label="Zoom in"><ZoomIn size={17} /></button><button type="button" onClick={() => setZoom((value) => Math.max(0.65, value - 0.15))} title="Zoom out" aria-label="Zoom out"><ZoomOut size={17} /></button><button type="button" onClick={() => { setZoom(1); setSearch(''); setActiveFilter('All'); }} title="Reset view" aria-label="Reset graph view"><Maximize2 size={16} /></button></div></div>
      {filters.length > 1 && <div className="knowledge-filters">{filters.map((filter) => <button type="button" key={filter} className={activeFilter === filter ? 'knowledge-filter active' : 'knowledge-filter'} onClick={() => setActiveFilter(filter)}>{filter}</button>)}</div>}
      {nodes.length ? <div className="knowledge-workspace">
        <section className="knowledge-graph-panel"><div className="knowledge-graph-topbar"><div><span className="knowledge-live-dot" /><span>API-RETURNED ENTITY RELATIONSHIPS</span></div><span className="knowledge-graph-hint">Select a node to inspect evidence</span></div>
          <div className="knowledge-svg-wrap"><svg className="knowledge-svg" viewBox={viewBox} role="img" aria-label="Persisted company knowledge graph">
            <defs><pattern id="nexus-knowledge-grid" width="32" height="32" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#a78bfa" opacity="0.16" /></pattern><filter id="nexus-knowledge-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="5" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
            <rect x="-1000" y="-1000" width="3000" height="3000" fill="url(#nexus-knowledge-grid)" />
            {visibleEdges.map((edge, index) => { const from = nodeById.get(edge.source); const to = nodeById.get(edge.target); if (!from || !to) return null; const active = edge.source === selectedId || edge.target === selectedId; return <g key={edge.id || `${edge.source}-${edge.target}-${index}`}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={active ? 'knowledge-edge selected' : 'knowledge-edge'} /><text x={(from.x + to.x) / 2} y={(from.y + to.y) / 2 - 8} className="knowledge-edge-label">{edgeLabel(edge).slice(0, 24)}</text></g>; })}
            {visibleNodes.map((node) => { const active = selectedId === node.id; const Icon = nodeIcons[node.type] || Network; return <g key={node.id} className={`knowledge-node ${active ? 'selected' : ''}`} transform={`translate(${node.x}, ${node.y})`} onClick={() => setSelectedId(node.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelectedId(node.id); }} role="button" tabIndex="0" aria-label={`${node.type}: ${node.label}`} style={{ '--node-color': nodeColors[node.type] || '#b8a8d8' }}><circle r={node.size + (active ? 15 : 7)} className="knowledge-node-ring" />{active && <circle r={node.size + 16} className="knowledge-node-halo" />}<circle r={node.size} className="knowledge-node-core" filter="url(#nexus-knowledge-glow)" /><text y={node.size + 22} className="knowledge-node-label">{node.label.length > 24 ? `${node.label.slice(0, 23)}…` : node.label}</text><text y={node.size + 38} className="knowledge-node-type">{node.type.toUpperCase()}</text><title>{node.label}</title><desc>{Icon.displayName || node.type}</desc></g>; })}
          </svg>{visibleNodes.length === 0 && <div className="knowledge-no-nodes"><Search size={25} /><h3>No entities match</h3><p>Adjust the search or entity filter.</p></div>}</div>
          <div className="knowledge-legend">{types.map((type) => <div className="knowledge-legend-item" key={type}><span style={{ background: nodeColors[type] || '#b8a8d8' }} />{type}</div>)}</div>
        </section>
        <aside className="knowledge-details"><div className="knowledge-details-heading"><div><span>ENTITY INSPECTOR</span><h3>Node details</h3></div><Network size={19} /></div>
          {selected ? <><div className="knowledge-selected-icon">{(() => { const Icon = nodeIcons[selected.type] || Network; return <Icon size={25} />; })()}</div><span className="knowledge-selected-type">{selected.type}</span><h2 className="knowledge-selected-title">{selected.label}</h2><p className="knowledge-selected-description">{selected.description || selected.publisher || 'No description is available in the API response.'}</p>
            {(selected.event_date || selected.stated_reason || selected.reported_outcome || selected.evidence_classification || selected.extraction_confidence != null) && <div className="knowledge-selected-facts">{selected.event_date && <p><strong>Event date:</strong> {selected.event_date}</p>}{selected.stated_reason && <p><strong>Stated reason:</strong> {selected.stated_reason}</p>}{selected.reported_outcome && <p><strong>Reported outcome:</strong> {selected.reported_outcome}</p>}{selected.evidence_classification && <p><strong>Classification:</strong> {selected.evidence_classification}</p>}{selected.extraction_confidence != null && <p><strong>Extraction confidence:</strong> {Math.round(Number(selected.extraction_confidence) * 100)}%</p>}</div>}
            {selected.url && <p><a href={selected.url} target="_blank" rel="noreferrer">Open original source</a></p>}{selected.permission_status && <p><strong>Permission:</strong> {selected.permission_status}</p>}
            <div className="knowledge-detail-divider" /><div className="knowledge-connection-heading"><span>DIRECT CONNECTIONS</span><strong>{selectedConnections.length}</strong></div><div className="knowledge-connection-list">{selectedConnections.length ? selectedConnections.map(({ edge, other, direction }, index) => <article className="knowledge-connection" key={edge.id || `${other.id}-${index}`}><div className="knowledge-connection-icon"><Network size={16} /></div><div className="knowledge-connection-text"><strong>{other.label}</strong><span>{direction === 'outgoing' ? edgeLabel(edge) : `connected via ${edgeLabel(edge)}`}</span><small>{edge.evidence_classification || edge.evidence_status || edge.provenance_status || 'Relationship classification unavailable'}</small>{edge.confidence != null && <small>Confidence {Math.round(Number(edge.confidence) * 100)}%</small>}{edge.warning && <small>{edge.warning}</small>}{edge.supporting_sources?.map((source) => <div key={source.source_id}><blockquote>{source.supporting_quote || 'Supporting quote unavailable.'}</blockquote>{source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">{source.source_title || 'Open supporting source'}</a>}</div>)}{other.url && <a href={other.url} target="_blank" rel="noreferrer">Open source</a>}</div></article>) : <p className="knowledge-no-connections">No evidence-backed relationships are available in this graph.</p>}</div>
          </> : <div className="knowledge-unselected"><Network size={30} /><h3>Select an entity</h3><p>Choose a returned graph node to inspect its stored details and provenance.</p></div>}
        </aside>
      </div> : <div className="knowledge-no-nodes"><h3>No persisted graph entities</h3><p>This company has no graph nodes in the current API response.</p></div>}
      <div className="knowledge-demo-notice"><Sparkles size={14} />Only nodes and relationships returned by the backend are displayed. Public graph scope excludes authorized internal sources; chronological order does not imply causation.</div>
    </div>
  );
}