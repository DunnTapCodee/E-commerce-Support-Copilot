import test from 'node:test';
import assert from 'node:assert/strict';

function findRepliedCustomerQuestion(msgs, currentIdx) {
  for (let i = currentIdx - 1; i >= 0; i--) {
    if (msgs[i]?.role === 'customer') {
      return msgs[i];
    }
  }
  return null;
}

function sortCustomersByNewestActivity(customers, activityMap) {
  return [...customers].sort((a, b) => {
    const actA = activityMap[a.id];
    const actB = activityMap[b.id];
    if (actA?.hasPendingDraft && !actB?.hasPendingDraft) return -1;
    if (!actA?.hasPendingDraft && actB?.hasPendingDraft) return 1;
    const timeA = actA?.updatedAt ? new Date(actA.updatedAt).getTime() : 0;
    const timeB = actB?.updatedAt ? new Date(actB.updatedAt).getTime() : 0;
    if (timeA !== timeB) return timeB - timeA;
    return 0;
  });
}

function extractPolicyCodes(text) {
  if (!text) return [];
  const matches = text.match(/POL-[A-Z0-9_-]+/gi) || [];
  return Array.from(new Set(matches.map((m) => m.toUpperCase())));
}

test('Layer 6 UI Unit: findRepliedCustomerQuestion links bot/staff reply to exact customer question (Messenger quote)', () => {
  const messages = [
    { id: '1', role: 'customer', content: 'Đơn hàng ORD-1100 của tôi đến đâu rồi?', timestamp: '10:00' },
    { id: '2', role: 'acknowledgement', content: 'Dạ em đang kiểm tra đơn cho mình ạ...', timestamp: '10:00' },
    { id: '3', role: 'agent', content: 'Dạ đơn ORD-1100 đã giao thành công theo [POL-ORD-001] ạ.', timestamp: '10:01' },
  ];

  const quotedForAck = findRepliedCustomerQuestion(messages, 1);
  assert.equal(quotedForAck?.id, '1');
  assert.equal(quotedForAck?.content, 'Đơn hàng ORD-1100 của tôi đến đâu rồi?');

  const quotedForAgent = findRepliedCustomerQuestion(messages, 2);
  assert.equal(quotedForAgent?.id, '1');
  assert.equal(quotedForAgent?.content, 'Đơn hàng ORD-1100 của tôi đến đâu rồi?');

  const quotedForFirstCustomer = findRepliedCustomerQuestion(messages, 0);
  assert.equal(quotedForFirstCustomer, null);
});

test('Layer 6 UI Unit: sortCustomersByNewestActivity puts pending drafts & newest questions at #1 top of Staff list', () => {
  const customers = [
    { id: 'CUST-1100', name: 'Lê Văn Sơn' },
    { id: 'CUST-1002', name: 'Phan Văn An' },
    { id: 'CUST-1001', name: 'Bùi Thị An' },
  ];

  const activityMap = {
    'CUST-1100': { updatedAt: '2026-11-18T08:00:00Z', hasPendingDraft: false },
    'CUST-1002': { updatedAt: '2026-11-18T09:30:00Z', hasPendingDraft: false },
    'CUST-1001': { updatedAt: '2026-11-18T08:45:00Z', hasPendingDraft: true },
  };

  const sorted = sortCustomersByNewestActivity(customers, activityMap);
  // CUST-1001 has a pending draft so must be #1; CUST-1002 has newer timestamp than CUST-1100 so must be #2
  assert.deepEqual(
    sorted.map((c) => c.id),
    ['CUST-1001', 'CUST-1002', 'CUST-1100']
  );
});

test('Layer 6 UI Unit: extractPolicyCodes extracts unique uppercase [POL-XXX] badges for Policy Modal viewer', () => {
  const msg = 'Dạ theo quy định [POL-RET-001] và (pol-ship-002), đơn hàng áp dụng [POL-RET-001] đổi trả 30 ngày.';
  const codes = extractPolicyCodes(msg);
  assert.deepEqual(codes, ['POL-RET-001', 'POL-SHIP-002']);
});
