import test, { after, before } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendRoot = path.resolve(__dirname, '..', '..', '..');
const sourceFile = path.join(frontendRoot, 'src', 'lib', 'chat-helpers.ts');
const tscBin = path.join(frontendRoot, 'node_modules', 'typescript', 'bin', 'tsc');

let tmpOutDir;
let helpers;

before(async () => {
  tmpOutDir = fs.mkdtempSync(path.join(os.tmpdir(), 'chat-helpers-unit-'));
  execFileSync(
    process.execPath,
    [
      tscBin,
      sourceFile,
      '--outDir',
      tmpOutDir,
      '--module',
      'esnext',
      '--target',
      'es2022',
      '--moduleResolution',
      'bundler',
      '--skipLibCheck',
    ],
    { cwd: frontendRoot, stdio: 'pipe' }
  );
  // tsc preserves directory structure under src/ or emits directly depending on rootDir
  const directOut = path.join(tmpOutDir, 'chat-helpers.js');
  const nestedOut = path.join(tmpOutDir, 'lib', 'chat-helpers.js');
  const compiledPath = fs.existsSync(directOut) ? directOut : nestedOut;
  helpers = await import(pathToFileURL(compiledPath).href);
});

after(() => {
  if (tmpOutDir && fs.existsSync(tmpOutDir)) {
    fs.rmSync(tmpOutDir, { recursive: true, force: true });
  }
});

test('findRepliedCustomerQuestion links bot/staff reply to exact preceding customer question', () => {
  const messages = [
    { id: '1', role: 'customer', content: 'Đơn hàng ORD-1100 của tôi đến đâu rồi?', timestamp: '10:00' },
    { id: '2', role: 'acknowledgement', content: 'Dạ em đang kiểm tra đơn cho mình ạ...', timestamp: '10:00' },
    { id: '3', role: 'agent', content: 'Dạ đơn ORD-1100 đã giao thành công theo [POL-ORD-001] ạ.', timestamp: '10:01' },
  ];

  const quotedForAck = helpers.findRepliedCustomerQuestion(messages, 1);
  assert.equal(quotedForAck?.id, '1');
  assert.equal(quotedForAck?.content, 'Đơn hàng ORD-1100 của tôi đến đâu rồi?');

  const quotedForAgent = helpers.findRepliedCustomerQuestion(messages, 2);
  assert.equal(quotedForAgent?.id, '1');

  assert.equal(helpers.findRepliedCustomerQuestion(messages, 0), null);
});

test('formatRepliedCustomerQuestionGroup collects consecutive customer messages for quote summary', () => {
  const messages = [
    { id: '1', role: 'customer', content: 'Cho hỏi đơn ORD-1002', timestamp: '10:00' },
    { id: '2', role: 'customer', content: 'Khi nào giao tới ạ?', timestamp: '10:01' },
    { id: '3', role: 'agent', content: 'Dạ đơn dự kiến giao hôm nay.', timestamp: '10:02' },
  ];
  assert.equal(
    helpers.formatRepliedCustomerQuestionGroup(messages, 2),
    'Cho hỏi đơn ORD-1002 • Khi nào giao tới ạ?'
  );
  assert.equal(helpers.formatRepliedCustomerQuestionGroup(messages, 0), null);
});

test('sortCustomersByNewestActivity sorts pending drafts first and supports both id and customer_id', () => {
  const activityMap = {
    'CUST-1100': { updatedAt: '2026-11-18T08:00:00Z', hasPendingDraft: false },
    'CUST-1002': { updatedAt: '2026-11-18T09:30:00Z', hasPendingDraft: false },
    'CUST-1001': { updatedAt: '2026-11-18T08:45:00Z', hasPendingDraft: true },
  };

  const sortedById = helpers.sortCustomersByNewestActivity(
    [{ id: 'CUST-1100' }, { id: 'CUST-1002' }, { id: 'CUST-1001' }],
    activityMap
  );
  assert.deepEqual(sortedById.map((c) => c.id), ['CUST-1001', 'CUST-1002', 'CUST-1100']);

  const sortedByCustomerId = helpers.sortCustomersByNewestActivity(
    [{ customer_id: 'CUST-1100' }, { customer_id: 'CUST-1002' }, { customer_id: 'CUST-1001' }],
    activityMap
  );
  assert.deepEqual(sortedByCustomerId.map((c) => c.customer_id), ['CUST-1001', 'CUST-1002', 'CUST-1100']);
});

test('extractPolicyCodes extracts unique uppercase [POL-XXX] badges', () => {
  const msg = 'Dạ theo quy định [POL-RET-001] và (pol-ship-002), đơn hàng áp dụng [POL-RET-001] đổi trả 30 ngày.';
  assert.deepEqual(helpers.extractPolicyCodes(msg), ['POL-RET-001', 'POL-SHIP-002']);
  assert.deepEqual(helpers.extractPolicyCodes(''), []);
});
