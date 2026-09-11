export const fixtureAssignmentId = "asg_fixture_biology";

export const assignmentFixtures = {
  empty: {
    error: {
      code: "assignment_not_found",
      message: "No worksheet has been added yet.",
      recoverable: true,
    },
  },
  loading: {
    assignment_id: fixtureAssignmentId,
    status: "analyzing",
    assignment_version: 1,
    version: 1,
    source: {
      filename: "biology-short-answer.pdf",
      page_count: 1,
    },
    progress: {
      state: "reading_pages",
      message: "Checking your worksheet…",
    },
  },
  ready: {
    assignment_id: fixtureAssignmentId,
    status: "ready",
    assignment_version: 2,
    version: 2,
    source: {
      filename: "biology-short-answer.pdf",
      title: "Photosynthesis and plant cells",
      page_count: 1,
    },
    question_count: 3,
    placement_summary: {
      inline_count: 2,
      answer_page_count: 1,
    },
    warnings: [
      "One answer will use an attached answer page if it does not fit safely.",
    ],
  },
  error: {
    error: {
      code: "requires_ocr",
      message:
        "This PDF appears to be scanned. Claros V2 supports PDFs with selectable text.",
      recoverable: true,
    },
  },
  documentViewer: {
    assignment_id: fixtureAssignmentId,
    assignment_version: 2,
    question_id: "q_01",
    question_index: 1,
    page_number: 1,
    question_text: "Why do plants need sunlight?",
    source_url: "/api/v2/fixtures/biology/source",
    fixture_source_url: "/fixtures/claros-biology-short-answer.pdf",
    source_status: "original_page_unchanged",
    source_sha256:
      "ccba948e849e849b80f4ce8f9d218e726b93a2efbb9eb730aabd5187e743b8d6",
    render_crop: {
      page_index: 0,
      rect: {
        origin: { x: 36, y: 28 },
        size: { width: 540, height: 270 },
      },
    },
  },
} as const;
