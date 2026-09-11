import { http, HttpResponse } from "msw";
import { assignmentFixtures, fixtureAssignmentId } from "./fixtures";

const assignmentUrl = `*/api/v2/assignments/${fixtureAssignmentId}`;

const responseHeaders = {
  ETag: '"assignment-version-2"',
  "Cache-Control": "no-store",
};

export const assignmentHandlers = {
  empty: [
    http.get(assignmentUrl, () =>
      HttpResponse.json(assignmentFixtures.empty, { status: 404 }),
    ),
  ],
  loading: [
    http.get(assignmentUrl, () =>
      HttpResponse.json(assignmentFixtures.loading, {
        headers: { ...responseHeaders, ETag: '"assignment-version-1"' },
      }),
    ),
  ],
  ready: [
    http.get(assignmentUrl, () =>
      HttpResponse.json(assignmentFixtures.ready, { headers: responseHeaders }),
    ),
  ],
  error: [
    http.get(assignmentUrl, () =>
      HttpResponse.json(assignmentFixtures.error, { status: 422 }),
    ),
  ],
  documentViewer: [
    http.get(`${assignmentUrl}/pages/1/context`, () =>
      HttpResponse.json(assignmentFixtures.documentViewer, {
        headers: responseHeaders,
      }),
    ),
  ],
} as const;

export const defaultHandlers = [
  ...assignmentHandlers.ready,
  ...assignmentHandlers.documentViewer,
];
