// Pure helpers for Web boot failure evidence. Never include URL userinfo, query or fragment.
const MAX_ENTRIES = 12;

export function safeResourceUrl(value) {
  try {
    const url = new URL(String(value));
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return '[non-http-url]';
    // origin strips credentials; pathname excludes query/fragment.
    return url.origin + url.pathname;
  } catch {
    return '[invalid-url]';
  }
}

export function safeDiagnosticText(value) {
  return String(value).replace(/https?:\/\/[^\s"'<>]+/g, safeResourceUrl).slice(0, 400);
}

export function boundedEvidence(values, limit = MAX_ENTRIES) {
  if (!Array.isArray(values)) return [];
  return values.slice(-limit).map((item) => safeDiagnosticText(item));
}

export function makeBootFailureReport({ stage, reason, dom, consoleErrors, pageErrors, failedRequests, failedResponses }) {
  return {
    stage: String(stage).slice(0, 80),
    reason: safeDiagnosticText(reason),
    dom: dom && typeof dom === 'object' ? {
      ready: dom.ready === true,
      canvasPresent: dom.canvasPresent === true,
      canvasReady: dom.canvasReady === true,
      bootPresent: dom.bootPresent === true,
      // Only event types, not message contents.
      events: boundedEvidence(dom.events),
    } : null,
    consoleErrors: boundedEvidence(consoleErrors),
    pageErrors: boundedEvidence(pageErrors),
    failedRequests: boundedEvidence(failedRequests),
    failedResponses: boundedEvidence(failedResponses),
  };
}
