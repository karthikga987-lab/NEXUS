import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Building2,
  FileClock,
  FileText,
  Layers,
  Maximize2,
  Network,
  Package,
  RotateCcw,
  ScanSearch,
  Search,
  Sparkles,
  Users,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import {
  GRAPH_CENTER,
  GRAPH_HEIGHT,
  GRAPH_WIDTH,
  SPHERE_RADIUS,
  nodeLabel,
  nodeType,
  projectPoint,
  relationshipStyle,
  sphericalNodePositions,
} from './knowledgeGraph3d.js';
import './KnowledgeGraph.css';

const nodeColors = {
  Company: '#c4b5fd',
  Product: '#a78bfa',
  Feature: '#8b9cff',
  'Customer Feedback': '#67e8d0',
  Source: '#fbbf75',
  Event: '#93c5fd',
  Proposal: '#f0abfc',
  'Proposal Analysis': '#fda4af',
  Entity: '#b8a8d8',
};

const nodeIcons = {
  Company: Building2,
  Product: Package,
  Feature: Layers,
  'Customer Feedback': Users,
  Source: FileText,
  Event: Sparkles,
  Proposal: FileClock,
  'Proposal Analysis': FileClock,
  Entity: Network,
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const edgeLabel = (edge) => String(
  edge.relation_type || edge.relationship_type || edge.type || 'Related',
).replaceAll('_', ' ');

function nodeSize(type) {
  if (type === 'Company') return 25;
  if (type === 'Event' || type === 'Proposal') return 16;
  return 13;
}

function sphereArcs(rotation, zoom) {
  const project = (point) => projectPoint(point, {
    ...rotation,
    zoom,
    width: GRAPH_WIDTH,
    height: GRAPH_HEIGHT,
  });
  const paths = [];
  const steps = 48;

  for (const latitudeDegrees of [-58, -30, 0, 30, 58]) {
    const latitude = (latitudeDegrees * Math.PI) / 180;
    const points = [];
    for (let step = 0; step <= steps; step += 1) {
      const longitude = (2 * Math.PI * step) / steps;
      points.push(project({
        x: SPHERE_RADIUS * Math.cos(latitude) * Math.cos(longitude),
        y: SPHERE_RADIUS * Math.sin(latitude),
        z: SPHERE_RADIUS * Math.cos(latitude) * Math.sin(longitude),
      }));
    }
    const depth = points.reduce((sum, point) => sum + point.z, 0) / points.length;
    paths.push({
      id: `latitude-${latitudeDegrees}`,
      d: points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' '),
      opacity: 0.06 + (clamp(depth / SPHERE_RADIUS, -1, 1) + 1) * 0.07,
    });
  }

  for (let longitudeIndex = 0; longitudeIndex < 8; longitudeIndex += 1) {
    const longitude = (Math.PI * longitudeIndex) / 8;
    const points = [];
    for (let step = 0; step <= steps; step += 1) {
      const latitude = -Math.PI / 2 + (Math.PI * step) / steps;
      points.push(project({
        x: SPHERE_RADIUS * Math.cos(latitude) * Math.cos(longitude),
        y: SPHERE_RADIUS * Math.sin(latitude),
        z: SPHERE_RADIUS * Math.cos(latitude) * Math.sin(longitude),
      }));
    }
    const depth = points.reduce((sum, point) => sum + point.z, 0) / points.length;
    paths.push({
      id: `longitude-${longitudeIndex}`,
      d: points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' '),
      opacity: 0.06 + (clamp(depth / SPHERE_RADIUS, -1, 1) + 1) * 0.07,
    });
  }

  return paths;
}

function truncateLabel(value, length = 22) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function EvidenceLinks({ sources = [] }) {
  if (!sources.length) return <p className="kg3d-muted">No supporting source provenance was returned for this edge.</p>;
  return (
    <div className="kg3d-evidence-list">
      {sources.map((source, index) => (
        <article key={source.source_id || index}>
          <blockquote>{source.supporting_quote || 'Supporting excerpt unavailable.'}</blockquote>
          <small>{source.publisher || source.source_title || 'Source publisher unavailable'}</small>
          {source.source_url && (
            <a href={source.source_url} target="_blank" rel="noreferrer">
              Open supporting source
            </a>
          )}
        </article>
      ))}
    </div>
  );
}

export default function KnowledgeGraph({ graph, loading = false }) {
  const [activeFilter, setActiveFilter] = useState('All');
  const [selectedId, setSelectedId] = useState('');
  const [selectedEdgeId, setSelectedEdgeId] = useState('');
  const [search, setSearch] = useState('');
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState({ yaw: -0.22, pitch: -0.12 });
  const [isDragging, setIsDragging] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const dragRef = useRef(null);

  const rawNodes = useMemo(
    () => (Array.isArray(graph?.nodes) ? graph.nodes : []),
    [graph?.nodes],
  );
  const rawEdges = useMemo(
    () => (Array.isArray(graph?.edges) ? graph.edges : []),
    [graph?.edges],
  );
  const companyId = rawNodes.find((node) => nodeType(node) === 'Company')?.company_id || '';
  const positions = useMemo(() => sphericalNodePositions(rawNodes), [rawNodes]);
  const positionedNodes = useMemo(() => rawNodes.map((node) => {
    const point = positions[node.id] || { x: 0, y: 0, z: 0 };
    const projection = projectPoint(point, {
      ...rotation,
      zoom,
      width: GRAPH_WIDTH,
      height: GRAPH_HEIGHT,
    });
    const type = nodeType(node);
    const depth = clamp((projection.z + SPHERE_RADIUS) / (2 * SPHERE_RADIUS), 0, 1);
    return {
      ...node,
      type,
      label: nodeLabel(node),
      x: projection.x,
      y: projection.y,
      z: projection.z,
      depth,
      size: nodeSize(type) * projection.perspective * zoom,
    };
  }).sort((left, right) => left.z - right.z), [rawNodes, positions, rotation, zoom]);

  const types = [...new Set(positionedNodes.map((node) => node.type))];
  const filters = ['All', ...types];
  const query = search.trim().toLowerCase();
  const visibleNodes = positionedNodes.filter((node) => {
    const text = `${node.label} ${node.type} ${node.description || ''} ${node.event_type || ''} ${node.publisher || ''}`.toLowerCase();
    return (activeFilter === 'All' || node.type === activeFilter) && (!query || text.includes(query));
  });
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const nodeById = new Map(positionedNodes.map((node) => [node.id, node]));
  const visibleEdges = rawEdges
    .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .map((edge) => ({
      ...edge,
      style: relationshipStyle(edge),
      sourceNode: nodeById.get(edge.source),
      targetNode: nodeById.get(edge.target),
    }))
    .sort((left, right) => (
      (left.sourceNode.z + left.targetNode.z) - (right.sourceNode.z + right.targetNode.z)
    ));
  const selected = nodeById.get(selectedId);
  const selectedEdge = rawEdges.find((edge) => edge.id === selectedEdgeId);
  const selectedConnections = selected
    ? rawEdges.map((edge) => {
      const isOutgoing = edge.source === selected.id;
      const otherId = isOutgoing ? edge.target : edge.source;
      return (isOutgoing || edge.target === selected.id)
        ? { edge, other: nodeById.get(otherId), direction: isOutgoing ? 'outgoing' : 'incoming' }
        : null;
    }).filter((item) => item?.other)
    : [];
  const arcs = useMemo(() => sphereArcs(rotation, zoom), [rotation, zoom]);

  useEffect(() => {
    if (!positionedNodes.some((node) => node.id === selectedId)) {
      setSelectedId(positionedNodes[0]?.id || '');
    }
  }, [positionedNodes, selectedId]);

  useEffect(() => {
    setSelectedEdgeId('');
    setRotation({ yaw: -0.22, pitch: -0.12 });
    setZoom(1);
  }, [companyId]);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setReducedMotion(preference.matches);
    updatePreference();
    preference.addEventListener?.('change', updatePreference);
    return () => preference.removeEventListener?.('change', updatePreference);
  }, []);

  useEffect(() => {
    if (reducedMotion || typeof window === 'undefined') return undefined;
    let frame = 0;
    let previousFrame = 0;
    const animate = (timestamp) => {
      if (timestamp - previousFrame >= 33) {
        const delta = previousFrame ? timestamp - previousFrame : 0;
        previousFrame = timestamp;
        if (!dragRef.current && delta) {
          setRotation((current) => ({ ...current, yaw: current.yaw + delta * 0.000075 }));
        }
      }
      frame = window.requestAnimationFrame(animate);
    };
    frame = window.requestAnimationFrame(animate);
    return () => window.cancelAnimationFrame(frame);
  }, [reducedMotion]);

  function startDrag(event) {
    if (event.button !== 0) return;
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setIsDragging(true);
  }

  function moveDrag(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.x;
    const deltaY = event.clientY - drag.y;
    drag.x = event.clientX;
    drag.y = event.clientY;
    setRotation((current) => ({
      yaw: current.yaw + deltaX * 0.008,
      pitch: clamp(current.pitch + deltaY * 0.008, -1.25, 1.25),
    }));
  }

  function endDrag(event) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setIsDragging(false);
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  }

  function resetView() {
    setRotation({ yaw: -0.22, pitch: -0.12 });
    setZoom(1);
    setSearch('');
    setActiveFilter('All');
    setSelectedEdgeId('');
  }

  if (loading && !graph) {
    return <div className="knowledge-no-nodes" role="status">Loading persisted graph data…</div>;
  }
  if (!graph) {
    return (
      <div className="knowledge-no-nodes" role="alert">
        <h3>Knowledge graph unavailable</h3>
        <p>The graph API did not return company data.</p>
      </div>
    );
  }

  return (
    <div className="knowledge-page">
      <header className="knowledge-heading">
        <div>
          <div className="knowledge-eyebrow"><Network size={14} /> CONNECTED INTELLIGENCE</div>
          <h2>Knowledge Graph</h2>
          <p>Rotate the evidence sphere to inspect persisted company knowledge and its supported connections.</p>
        </div>
        <div className="knowledge-node-total">
          <span>RETURNED ENTITIES</span>
          <strong>{visibleNodes.length}</strong>
          <small>{visibleEdges.length} relationships in view</small>
        </div>
      </header>

      <div className="knowledge-toolbar">
        <label className="knowledge-search">
          <Search size={17} />
          <input
            type="search"
            placeholder="Search persisted entities…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Search knowledge graph"
          />
        </label>
        <div className="knowledge-controls">
          <button type="button" onClick={() => setZoom((value) => clamp(value + 0.12, 0.65, 1.55))} title="Zoom in" aria-label="Zoom in"><ZoomIn size={17} /></button>
          <button type="button" onClick={() => setZoom((value) => clamp(value - 0.12, 0.65, 1.55))} title="Zoom out" aria-label="Zoom out"><ZoomOut size={17} /></button>
          <button type="button" onClick={() => { setRotation({ yaw: -0.22, pitch: -0.12 }); setZoom(1); }} title="Fit sphere to view" aria-label="Fit graph to view"><ScanSearch size={16} /></button>
          <button type="button" onClick={resetView} title="Reset camera, filters, and search" aria-label="Reset graph view"><RotateCcw size={16} /></button>
        </div>
      </div>

      {filters.length > 1 && (
        <div className="knowledge-filters" aria-label="Filter graph entities">
          {filters.map((filter) => (
            <button
              type="button"
              key={filter}
              className={activeFilter === filter ? 'knowledge-filter active' : 'knowledge-filter'}
              onClick={() => setActiveFilter(filter)}
            >
              {filter}
            </button>
          ))}
        </div>
      )}

      {rawNodes.length ? (
        <div className="knowledge-workspace">
          <section className="knowledge-graph-panel" aria-label="Interactive company knowledge sphere">
            <div className="knowledge-graph-topbar">
              <div><span className="knowledge-live-dot" /> PERSISTED COMPANY GRAPH</div>
              <span className="knowledge-graph-hint">Drag to rotate · scroll to zoom · select nodes or edges</span>
            </div>
            <div
              className={`kg3d-viewport${isDragging ? ' is-dragging' : ''}`}
              onPointerDown={startDrag}
              onPointerMove={moveDrag}
              onPointerUp={endDrag}
              onPointerCancel={endDrag}
              onWheel={(event) => {
                event.preventDefault();
                setZoom((value) => clamp(value - Math.sign(event.deltaY) * 0.08, 0.65, 1.55));
              }}
              role="application"
              aria-label="Drag the three-dimensional graph sphere to rotate it"
            >
              <svg
                className="kg3d-svg"
                viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
                preserveAspectRatio="xMidYMid meet"
                role="img"
                aria-label="Three-dimensional projection of persisted company nodes and relationships"
              >
                <defs>
                  <radialGradient id="nexus-graph-sphere" cx="34%" cy="27%" r="76%">
                    <stop offset="0%" stopColor="#514178" stopOpacity="0.66" />
                    <stop offset="54%" stopColor="#1b1630" stopOpacity="0.43" />
                    <stop offset="100%" stopColor="#080b14" stopOpacity="0.14" />
                  </radialGradient>
                  <radialGradient id="nexus-graph-light" cx="31%" cy="26%" r="63%">
                    <stop offset="0%" stopColor="#c4b5fd" stopOpacity="0.24" />
                    <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0" />
                  </radialGradient>
                  <filter id="nexus-graph-glow" x="-150%" y="-150%" width="400%" height="400%">
                    <feGaussianBlur stdDeviation="4" result="blur" />
                    <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                  </filter>
                </defs>
                <rect width={GRAPH_WIDTH} height={GRAPH_HEIGHT} fill="#080b14" />
                <circle cx={GRAPH_CENTER.x} cy={GRAPH_CENTER.y} r={SPHERE_RADIUS * zoom} fill="url(#nexus-graph-sphere)" />
                <circle cx={GRAPH_CENTER.x} cy={GRAPH_CENTER.y} r={SPHERE_RADIUS * zoom} fill="url(#nexus-graph-light)" />
                <circle className="kg3d-sphere-outline" cx={GRAPH_CENTER.x} cy={GRAPH_CENTER.y} r={SPHERE_RADIUS * zoom} />
                <g className="kg3d-wireframe" aria-hidden="true">
                  {arcs.map((arc) => <path key={arc.id} d={arc.d} opacity={arc.opacity} />)}
                </g>

                <g className="kg3d-edges">
                  {visibleEdges.map((edge) => {
                    const isSelected = selectedEdgeId === edge.id;
                    const meanDepth = (edge.sourceNode.depth + edge.targetNode.depth) / 2;
                    const opacity = isSelected ? 0.96 : 0.16 + meanDepth * 0.5;
                    const title = `${edgeLabel(edge)} · ${edge.evidence_classification || edge.evidence_status || 'classification unavailable'}`;
                    return (
                      <g
                        key={edge.id || `${edge.source}-${edge.target}`}
                        className={`kg3d-edge ${edge.style.kind}${isSelected ? ' selected' : ''}`}
                        role="button"
                        tabIndex={0}
                        aria-label={`Relationship ${title}`}
                        data-graph-interactive="true"
                        onPointerDown={(event) => event.stopPropagation()}
                        onClick={() => { setSelectedEdgeId(edge.id); setSelectedId(''); }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            setSelectedEdgeId(edge.id);
                            setSelectedId('');
                          }
                        }}
                      >
                        <title>{title}</title>
                        <line
                          x1={edge.sourceNode.x}
                          y1={edge.sourceNode.y}
                          x2={edge.targetNode.x}
                          y2={edge.targetNode.y}
                          stroke={edge.style.color}
                          strokeDasharray={edge.style.dash || undefined}
                          opacity={opacity}
                          strokeWidth={isSelected ? 2.7 : 1.35}
                          pointerEvents="none"
                        />
                        <line
                          x1={edge.sourceNode.x}
                          y1={edge.sourceNode.y}
                          x2={edge.targetNode.x}
                          y2={edge.targetNode.y}
                          stroke="transparent"
                          strokeWidth="12"
                          pointerEvents="stroke"
                        />
                      </g>
                    );
                  })}
                </g>

                <g className="kg3d-nodes">
                  {visibleNodes.map((node) => {
                    const active = selectedId === node.id;
                    const Icon = nodeIcons[node.type] || Network;
                    const color = nodeColors[node.type] || nodeColors.Entity;
                    const showLabel = active || node.depth > 0.55;
                    const scale = 0.28 + node.depth * 0.72;
                    return (
                      <g
                        key={node.id}
                        className={`kg3d-node${active ? ' selected' : ''}${node.type === 'Company' ? ' company' : ''}`}
                        transform={`translate(${node.x.toFixed(1)},${node.y.toFixed(1)})`}
                        style={{ '--node-color': color, '--node-depth': scale }}
                        role="button"
                        tabIndex={0}
                        aria-label={`${node.type}: ${node.label}`}
                        data-graph-interactive="true"
                        onPointerDown={(event) => event.stopPropagation()}
                        onClick={() => { setSelectedId(node.id); setSelectedEdgeId(''); }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            setSelectedId(node.id);
                            setSelectedEdgeId('');
                          }
                        }}
                      >
                        <title>{`${node.type}: ${node.label}${node.description ? ` — ${node.description}` : ''}`}</title>
                        <circle r={node.size + (active ? 10 : 5)} className="kg3d-node-halo" opacity={Math.max(0.22, node.depth)} />
                        <circle r={node.size + 2} className="kg3d-node-core" filter="url(#nexus-graph-glow)" />
                        {node.type === 'Company' ? (
                          <foreignObject x={-node.size * 0.58} y={-node.size * 0.58} width={node.size * 1.16} height={node.size * 1.16} pointerEvents="none">
                            <div className="kg3d-company-icon"><Icon size={node.size * 1.05} /></div>
                          </foreignObject>
                        ) : (
                          <circle r={Math.max(3.5, node.size * 0.23)} className="kg3d-node-light" />
                        )}
                        {showLabel && (
                          <>
                            <text y={node.size + 17} className="kg3d-node-label">{truncateLabel(node.label, active ? 30 : 18)}</text>
                            <text y={node.size + 31} className="kg3d-node-type">{node.type.toUpperCase()}</text>
                          </>
                        )}
                      </g>
                    );
                  })}
                </g>
              </svg>
              {visibleNodes.length === 0 && (
                <div className="knowledge-no-nodes kg3d-no-match">
                  <Search size={25} />
                  <h3>No entities match</h3>
                  <p>Adjust the search or entity filter.</p>
                </div>
              )}
              <div className="kg3d-depth-label" aria-hidden="true">3D SPHERICAL VIEW</div>
            </div>
            <div className="knowledge-legend">
              {types.map((type) => (
                <div className="knowledge-legend-item" key={type}>
                  <span style={{ background: nodeColors[type] || nodeColors.Entity }} />{type}
                </div>
              ))}
              <div className="knowledge-legend-item"><i className="kg3d-line-key causal" /> Documented causal relationship</div>
              <div className="knowledge-legend-item"><i className="kg3d-line-key correlation" /> Correlation / sequence</div>
              <div className="knowledge-legend-item"><i className="kg3d-line-key unverified" /> Unknown / missing provenance</div>
            </div>
          </section>

          <aside className="knowledge-details" aria-live="polite">
            <div className="knowledge-details-heading">
              <div><span>ENTITY INSPECTOR</span><h3>{selectedEdge ? 'Relationship details' : 'Node details'}</h3></div>
              <Network size={19} />
            </div>

            {selectedEdge ? (
              <div className="kg3d-inspector-content">
                <span className="knowledge-selected-type">{edgeLabel(selectedEdge)}</span>
                <h2 className="knowledge-selected-title">{selectedEdge.explanation || edgeLabel(selectedEdge)}</h2>
                <p><strong>Evidence classification:</strong> {selectedEdge.evidence_classification || selectedEdge.evidence_status || 'Unavailable'}</p>
                {selectedEdge.confidence != null && <p><strong>Confidence:</strong> {(Number(selectedEdge.confidence) * 100).toFixed(1)}%</p>}
                {selectedEdge.provenance_status && <p><strong>Provenance:</strong> {selectedEdge.provenance_status}</p>}
                {selectedEdge.warning && <p className="kg3d-warning">{selectedEdge.warning}</p>}
                <div className="knowledge-detail-divider" />
                <strong>Supporting evidence</strong>
                <EvidenceLinks sources={selectedEdge.supporting_sources || []} />
              </div>
            ) : selected ? (
              <div className="kg3d-inspector-content">
                <div className="knowledge-selected-icon" style={{ '--node-color': nodeColors[selected.type] || nodeColors.Entity }}>
                  {(() => { const Icon = nodeIcons[selected.type] || Network; return <Icon size={24} />; })()}
                </div>
                <span className="knowledge-selected-type">{selected.type}</span>
                <h2 className="knowledge-selected-title">{selected.label}</h2>
                <p className="knowledge-selected-description">{selected.description || selected.publisher || 'No description is available in the API response.'}</p>
                <div className="kg3d-facts">
                  {selected.event_date && <p><strong>Event date:</strong> {selected.event_date}</p>}
                  {selected.node_type === 'event' && !selected.event_date && <p><strong>Event date:</strong> Unknown in the available source evidence</p>}
                  {selected.event_type && <p><strong>Event type:</strong> {String(selected.event_type).replaceAll('_', ' ')}</p>}
                  {selected.stated_reason && <p><strong>Stated reason:</strong> {selected.stated_reason}</p>}
                  {selected.reported_outcome && <p><strong>Reported outcome:</strong> {selected.reported_outcome}</p>}
                  {selected.evidence_classification && <p><strong>Classification:</strong> {selected.evidence_classification}</p>}
                  {selected.extraction_confidence != null && <p><strong>Extraction confidence:</strong> {(Number(selected.extraction_confidence) * 100).toFixed(1)}%</p>}
                  {selected.processing_status && <p><strong>Processing:</strong> {selected.processing_status}</p>}
                  {selected.permission_status && <p><strong>Permission:</strong> {selected.permission_status}</p>}
                  {selected.proposal_status && <p><strong>Submission:</strong> {selected.proposal_status}</p>}
                  {selected.analysis_status && <p><strong>Analysis:</strong> {selected.analysis_status}</p>}
                </div>
                {selected.node_type === 'proposal' && (
                  <p className="kg3d-warning">{selected.interpretation_warning || 'User-submitted proposal; not historical company evidence.'}</p>
                )}
                {(selected.url || selected.source_url) && (
                  <a href={selected.url || selected.source_url} target="_blank" rel="noreferrer">Open original source</a>
                )}
                {Array.isArray(selected.source_ids) && selected.source_ids.length > 0 && (
                  <p className="kg3d-muted">Supporting source IDs: {selected.source_ids.join(', ')}</p>
                )}
                <div className="knowledge-detail-divider" />
                <div className="knowledge-connection-heading"><span>DIRECT CONNECTIONS</span><strong>{selectedConnections.length}</strong></div>
                <div className="knowledge-connection-list">
                  {selectedConnections.length ? selectedConnections.map(({ edge, other, direction }, index) => (
                    <button
                      type="button"
                      className="knowledge-connection"
                      key={edge.id || `${other.id}-${index}`}
                      onClick={() => setSelectedEdgeId(edge.id)}
                    >
                      <span className="knowledge-connection-icon"><Network size={16} /></span>
                      <span className="knowledge-connection-text">
                        <strong>{other.label}</strong>
                        <span>{direction === 'outgoing' ? edgeLabel(edge) : `connected via ${edgeLabel(edge)}`}</span>
                        <small>{edge.evidence_classification || edge.evidence_status || edge.provenance_status || 'Relationship classification unavailable'}</small>
                      </span>
                    </button>
                  )) : <p className="knowledge-no-connections">No returned relationships are directly linked to this entity.</p>}
                </div>
              </div>
            ) : (
              <div className="knowledge-unselected">
                <Network size={30} />
                <h3>Select a node or edge</h3>
                <p>Inspect persisted entity details, relationship classifications, and source provenance.</p>
              </div>
            )}
          </aside>
        </div>
      ) : (
        <div className="knowledge-no-nodes">
          <h3>No persisted graph entities</h3>
          <p>This company has no graph nodes in the current API response.</p>
        </div>
      )}

      <div className="knowledge-demo-notice"><Sparkles size={14} />Only backend-returned records are displayed. Causal links retain their evidence classification; chronological sequence is not shown as causation.</div>
    </div>
  );
}
