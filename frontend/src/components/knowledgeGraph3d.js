export const GRAPH_WIDTH = 920;
export const GRAPH_HEIGHT = 570;
export const GRAPH_CENTER = { x: GRAPH_WIDTH / 2, y: GRAPH_HEIGHT / 2 };
export const SPHERE_RADIUS = 188;

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

export function nodeType(node) {
  const value = String(node.node_type || node.type || node.entity_type || 'entity').toLowerCase();
  if (value.includes('company')) return 'Company';
  if (value.includes('source') || value.includes('document')) return 'Source';
  if (value.includes('event')) return 'Event';
  if (value.includes('analysis')) return 'Proposal Analysis';
  if (value.includes('proposal')) return 'Proposal';
  if (value.includes('product')) return 'Product';
  if (value.includes('feature')) return 'Feature';
  if (value.includes('feedback') || value.includes('customer')) return 'Customer Feedback';
  return 'Entity';
}

export function nodeLabel(node) {
  return String(
    node.title
      || node.name
      || node.product_name
      || node.label
      || node.id
      || 'Unnamed entity',
  );
}

/** Put the selected company at the origin and distribute the returned nodes on a 3D sphere. */
export function sphericalNodePositions(nodes, radius = SPHERE_RADIUS * 0.88) {
  const companyIndex = nodes.findIndex((node) => nodeType(node) === 'Company');
  const outerCount = Math.max(0, nodes.length - (companyIndex >= 0 ? 1 : 0));
  let outerIndex = 0;

  return Object.fromEntries(nodes.map((node, index) => {
    if (index === companyIndex) return [node.id, { x: 0, y: 0, z: 0, isCompany: true }];

    const y = outerCount <= 1
      ? 0
      : 1 - (2 * (outerIndex + 0.5)) / outerCount;
    const horizontalRadius = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = GOLDEN_ANGLE * outerIndex;
    const point = {
      x: Math.cos(theta) * horizontalRadius * radius,
      y: y * radius,
      z: Math.sin(theta) * horizontalRadius * radius,
      isCompany: false,
    };
    outerIndex += 1;
    return [node.id, point];
  }));
}

export function rotatePoint(point, yaw = 0, pitch = 0) {
  const cosYaw = Math.cos(yaw);
  const sinYaw = Math.sin(yaw);
  const yawX = point.x * cosYaw + point.z * sinYaw;
  const yawZ = -point.x * sinYaw + point.z * cosYaw;
  const cosPitch = Math.cos(pitch);
  const sinPitch = Math.sin(pitch);
  return {
    x: yawX,
    y: point.y * cosPitch - yawZ * sinPitch,
    z: point.y * sinPitch + yawZ * cosPitch,
  };
}

/** Perspective-project a rotated 3D point onto the responsive SVG viewport. */
export function projectPoint(
  point,
  { yaw = 0, pitch = 0, zoom = 1, width = GRAPH_WIDTH, height = GRAPH_HEIGHT, focalLength = 650 } = {},
) {
  const rotated = rotatePoint(point, yaw, pitch);
  const denominator = Math.max(1, focalLength - rotated.z * zoom);
  const perspective = focalLength / denominator;
  return {
    x: width / 2 + rotated.x * zoom * perspective,
    y: height / 2 + rotated.y * zoom * perspective,
    z: rotated.z,
    perspective,
  };
}

export function relationshipStyle(edge) {
  const relation = String(edge.relation_type || edge.relationship_type || edge.type || '').toUpperCase();
  const classification = String(edge.evidence_classification || edge.evidence_status || '').toLowerCase();
  if (classification === 'correlation' || relation === 'PRECEDED_BY') {
    return { kind: 'correlation', color: '#fbbf75', dash: '5 5' };
  }
  if (classification === 'unknown' || edge.provenance_status === 'relationship_source_provenance_missing') {
    return { kind: 'unverified', color: '#94a3b8', dash: '2 6' };
  }
  if (['MOTIVATED_BY', 'RESULTED_IN', 'CHANGED_BECAUSE_OF'].includes(relation)) {
    return { kind: 'causal', color: '#fb7185', dash: '' };
  }
  return { kind: 'supported', color: '#a78bfa', dash: '' };
}
