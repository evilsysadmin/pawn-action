import test from 'node:test';
import assert from 'node:assert/strict';
import { safeResourceUrl, safeDiagnosticText, boundedEvidence, makeBootFailureReport } from '../scripts/pawn_action_boot_diagnostics.mjs';

test('Web boot diagnostics never expose auth from failed resource URL', () => {
  assert.equal(safeResourceUrl('https://alice:secret@example.test/atlas.png?token=supersecret#x'), 'https://example.test/atlas.png');
  assert.equal(safeResourceUrl('javascript:alert(1)'), '[non-http-url]');
  assert.equal(safeResourceUrl('not a url'), '[invalid-url]');
  assert.equal(safeDiagnosticText('GET https://test:pw@example.test/atlas.pck?jwt=secret failed'), 'GET https://example.test/atlas.pck failed');
});

test('failure report is bounded and distinguishes missing ready from missing canvas', () => {
  const report = makeBootFailureReport({
    stage: 'industrial_front_v1', reason: 'waitForFunction timed out',
    dom: { ready: false, canvasPresent: true, canvasReady: false, bootPresent: true, events: ['load-error'] },
    consoleErrors: Array.from({ length: 30 }, (_, i) => 'error-' + i),
    pageErrors: [], failedRequests: ['https://example.test/index.wasm'], failedResponses: [],
  });
  assert.equal(report.dom.ready, false);
  assert.equal(report.dom.canvasPresent, true);
  assert.equal(report.dom.events[0], 'load-error');
  assert.equal(report.consoleErrors.length, 12);
  assert.equal(report.consoleErrors[0], 'error-18');
  assert.deepEqual(boundedEvidence(null), []);
});
