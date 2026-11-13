import test from 'node:test';
import assert from 'node:assert/strict';

import {
  GRAPH_CENTER,
  SPHERE_RADIUS,
  projectPoint,
  relationshipStyle,
  rotatePoint,
  sphericalNodePositions,
} from '../src/components/knowledgeGraph3d.js';

test('company is central and returned entities occupy distinct 3D sphere positions', () => {
  const nodes = [
    { id: 'company:1', node_type: 'company' },
    { id: 'event:1', node_type: 'event' },
    { id: 'source:1', node_type: 'source' },
    { id: 'proposal:1', node_type: 'proposal' },
  ];
  const positions = sphericalNodePositions(nodes);

  assert.deepEqual(positions['company:1'], { x: 0, y: 0, z: 0, isCompany: true });
  for (const id of ['event:1', 'source:1', 'proposal:1']) {
    const point = positions[id];
    const length = Math.hypot(point.x, point.y, point.z);
    assert.ok(Math.abs(length - SPHERE_RADIUS * 0.88) < 1e-8);
  }
  assert.notDeepEqual(positions['event:1'], positions['source:1']);
});

test('3D rotation preserves distance from sphere center', () => {
  const point = { x: 20, y: -45, z: 80 };
  const rotated = rotatePoint(point, 1.1, -0.6);

  assert.ok(Math.abs(Math.hypot(point.x, point.y, point.z) - Math.hypot(rotated.x, rotated.y, rotated.z)) < 1e-8);
});

test('perspective projection responds to depth, yaw, and zoom', () => {
  const point = { x: 40, y: 5, z: 120 };
  const front = projectPoint(point, { yaw: 0, zoom: 1 });
  const rotated = projectPoint(point, { yaw: Math.PI / 2, zoom: 1 });
  const zoomed = projectPoint(point, { yaw: 0, zoom: 1.3 });

  assert.notEqual(front.x, rotated.x);
  assert.notEqual(front.x, zoomed.x);
  assert.equal(projectPoint({ x: 0, y: 0, z: 0 }).x, GRAPH_CENTER.x);
});

test('relationship styles distinguish causation, correlation, and unknown evidence', () => {
  assert.equal(relationshipStyle({ relation_type: 'RESULTED_IN', evidence_status: 'documented_cause' }).kind, 'causal');
  assert.equal(relationshipStyle({ relation_type: 'PRECEDED_BY', evidence_status: 'correlation' }).kind, 'correlation');
  assert.equal(relationshipStyle({ relation_type: 'APPROVED_BY', evidence_status: 'unknown' }).kind, 'unverified');
});
