/**
 * Table-driven checks for frontend/session-rules.js (run: npm run test:session-rules).
 */
'use strict';

const assert = require('assert');
const path = require('path');

const rules = require(path.join(__dirname, '..', 'frontend', 'session-rules.js'));

const cases = [
  {
    raw: 'Please export PDF now.',
    writeIntent: false,
    answerStated: false,
    exportIntent: true,
    questionNum: null,
  },
  {
    raw: 'Save this as PDF please.',
    writeIntent: false,
    answerStated: false,
    exportIntent: true,
    questionNum: null,
  },
  {
    raw: 'Write my answer for question 2.',
    writeIntent: true,
    answerStated: false,
    exportIntent: false,
    questionNum: 2,
  },
  {
    raw: 'My answer is 42 for question 3.',
    writeIntent: false,
    answerStated: true,
    exportIntent: false,
    questionNum: 3,
  },
  {
    raw: 'I think it is the Civil War.',
    writeIntent: false,
    answerStated: true,
    exportIntent: false,
    questionNum: null,
  },
  {
    raw: 'Let me write that for question 1',
    writeIntent: true,
    answerStated: false,
    exportIntent: false,
    questionNum: 1,
    clarosWriteQ: 1,
  },
];

for (const c of cases) {
  const norm = rules.normalizeTranscript(c.raw);
  assert.strictEqual(rules.WRITE_INTENT_RE.test(norm), c.writeIntent, `writeIntent ${c.raw}`);
  assert.strictEqual(rules.ANSWER_STATED_RE.test(norm), c.answerStated, `answerStated ${c.raw}`);
  assert.strictEqual(rules.hasExportIntent(norm), c.exportIntent, `exportIntent ${c.raw}`);
  const qm = rules.QUESTION_NUM_RE.exec(norm);
  const num = qm ? parseInt(qm[1], 10) : null;
  assert.strictEqual(num, c.questionNum, `questionNum ${c.raw}`);
  if (c.clarosWriteQ != null) {
    const m = rules.CLAROS_WRITE_PHRASE_RE.exec(norm);
    assert.ok(m, `claros phrase should match: ${c.raw}`);
    assert.strictEqual(parseInt(m[1], 10), c.clarosWriteQ);
  }
}

console.log('session-rules.test.cjs: all', cases.length, 'cases passed.');
