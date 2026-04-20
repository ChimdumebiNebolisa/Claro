/**
 * Pure string helpers for voice/write/export intent (browser + Node tests).
 * Loaded in index.html before the main app script; also require()'d from tests/session-rules.test.cjs.
 */
'use strict';

function normalizeTranscript(text) {
  if (!text) return '';
  var s = String(text)
    .toLowerCase()
    .trim()
    .replace(/[.,!?;:"]/g, ' ')
    .replace(/\s+/g, ' ');
  return s;
}

var WRITE_INTENT_RE = /\b(write|put\s+that\s+down|answer\s+question|write\s+my\s+answer|write\s+it\s+down|write\s+that)\b/;
var QUESTION_NUM_RE = /question\s*(\d+)/;
var CLAROS_WRITE_PHRASE_RE = /let me write that for question\s*(\d+)/i;
var ANSWER_STATED_RE = /(?:my|the|final)\s+answer\s+is\b|i\s+think\s+(?:its|it\s+is|the\s+answer\s+is)\b|(?:my|the)\s+final\s+answer\b|thats\s+my\s+answer\b|so\s+(?:its|it\s+is|the\s+answer\s+is)\b/;

function hasExportIntent(norm) {
  if (!norm) return false;
  return norm.indexOf('export pdf') !== -1 ||
    norm.indexOf('export as pdf') !== -1 ||
    norm.indexOf('export this as pdf') !== -1 ||
    norm.indexOf('download pdf') !== -1 ||
    norm.indexOf('download the pdf') !== -1 ||
    norm.indexOf('save as pdf') !== -1 ||
    norm.indexOf('save this as pdf') !== -1 ||
    norm.indexOf('save it as pdf') !== -1;
}

var ClarosSessionRules = {
  normalizeTranscript: normalizeTranscript,
  hasExportIntent: hasExportIntent,
  WRITE_INTENT_RE: WRITE_INTENT_RE,
  QUESTION_NUM_RE: QUESTION_NUM_RE,
  CLAROS_WRITE_PHRASE_RE: CLAROS_WRITE_PHRASE_RE,
  ANSWER_STATED_RE: ANSWER_STATED_RE,
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = ClarosSessionRules;
}
