import type { ChatMessage } from '../types';

export interface CustomerActivityMeta {
  updatedAt: string;
  hasPendingDraft: boolean;
  lastTitle?: string;
  messageCount?: number;
}

/**
 * Find the most recent preceding customer message that a staff/agent/bot message is replying to.
 * Used to render the Messenger-style faded quoted question above each reply bubble.
 */
export function findRepliedCustomerQuestion(
  msgs: ChatMessage[],
  currentIdx: number
): ChatMessage | null {
  for (let i = currentIdx - 1; i >= 0; i--) {
    if (msgs[i]?.role === 'customer') {
      return msgs[i];
    }
  }
  return null;
}

/**
 * Summarize consecutive preceding customer questions joined with ' • ' for Customer Portal quote previews.
 */
export function formatRepliedCustomerQuestionGroup(
  msgs: ChatMessage[],
  currentIdx: number
): string | null {
  const collected: string[] = [];
  for (let i = currentIdx - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m?.role === 'customer') {
      collected.unshift(m.content);
    } else if (collected.length > 0) {
      break;
    }
  }
  return collected.length > 0 ? collected.join(' • ') : null;
}

/**
 * Sort customers so that:
 * 1. Customers with a pending Copilot draft / unanswered question appear FIRST.
 * 2. Customers with the newest question/session `updatedAt` appear next (descending).
 */
export function sortCustomersByNewestActivity<T extends { id?: string; customer_id?: string }>(
  customers: T[],
  activityMap: Record<string, CustomerActivityMeta>
): T[] {
  const getKey = (item: T) => item.id ?? item.customer_id ?? '';
  return [...customers].sort((a, b) => {
    const actA = activityMap[getKey(a)];
    const actB = activityMap[getKey(b)];
    if (actA?.hasPendingDraft && !actB?.hasPendingDraft) return -1;
    if (!actA?.hasPendingDraft && actB?.hasPendingDraft) return 1;
    const timeA = actA?.updatedAt ? new Date(actA.updatedAt).getTime() : 0;
    const timeB = actB?.updatedAt ? new Date(actB.updatedAt).getTime() : 0;
    if (timeA !== timeB) return timeB - timeA;
    return 0;
  });
}

/**
 * Extract unique uppercase policy document codes (e.g. ['POL-RET-001', 'POL-SHIP-001']) from message text.
 */
export function extractPolicyCodes(text: string): string[] {
  if (!text) return [];
  const matches = text.match(/POL-[A-Z0-9_-]+/gi) || [];
  return Array.from(new Set(matches.map((m) => m.toUpperCase())));
}
