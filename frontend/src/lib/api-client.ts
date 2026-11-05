import {
  GatewayResponse,
  PolicyAuditLogEntry,
  PolicyFilterResult,
  RetrievedDocument,
} from '../types';

const API_BASE = '/api/v1/copilot';

export const apiClient = {
  // Chat & Copilot Ingress
  async sendQuery(query: string, sessionId: string, customerId?: string): Promise<GatewayResponse> {
    const res = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        session_id: sessionId,
        customer_id: customerId,
      }),
    });
    if (!res.ok) {
      throw new Error(`Gateway Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async recordAction(payload: {
    interaction_id: string;
    action: 'APPROVE' | 'EDIT' | 'REJECT' | 'ESCALATE';
    final_text?: string;
    agent_notes?: string;
    handling_time_ms?: number;
  }): Promise<void> {
    await fetch(`${API_BASE}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  // Document & Policy Lifecycle (Proxied through Gateway to Document Service)
  async filterPolicy(rawText: string, suggestedCategory?: string): Promise<PolicyFilterResult> {
    const res = await fetch(`${API_BASE}/policy/filter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_text: rawText,
        suggested_category: suggestedCategory,
      }),
    });
    if (!res.ok) {
      throw new Error(`Filter Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async createPolicy(policy: RetrievedDocument, reason?: string): Promise<RetrievedDocument> {
    const res = await fetch(`${API_BASE}/policy/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        policy,
        performed_by: 'Nhân viên CSKH (Web)',
        reason: reason || 'Tạo mới qua Web UI',
      }),
    });
    if (!res.ok) {
      throw new Error(`Create Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async listPolicies(): Promise<RetrievedDocument[]> {
    const res = await fetch(`${API_BASE}/policies`);
    if (!res.ok) {
      throw new Error(`List Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async updatePolicy(docId: string, updates: Partial<RetrievedDocument>): Promise<RetrievedDocument> {
    const res = await fetch(`${API_BASE}/policies/${docId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...updates,
        performed_by: 'Nhân viên CSKH (Web)',
      }),
    });
    if (!res.ok) {
      throw new Error(`Update Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async deletePolicy(docId: string): Promise<void> {
    const res = await fetch(`${API_BASE}/policies/${docId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      throw new Error(`Delete Error (${res.status}): ${await res.text()}`);
    }
  },

  async listAuditLogs(): Promise<PolicyAuditLogEntry[]> {
    const res = await fetch(`${API_BASE}/policies/audit-logs`);
    if (!res.ok) {
      throw new Error(`Audit Logs Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async rollbackPolicy(logId: string): Promise<RetrievedDocument> {
    const res = await fetch(`${API_BASE}/policies/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        log_id: logId,
        performed_by: 'Nhân viên CSKH (Rollback)',
        reason: `Hoàn tác qua Web UI theo Log ID ${logId}`,
      }),
    });
    if (!res.ok) {
      throw new Error(`Rollback Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async syncActiveStatus(): Promise<any> {
    const res = await fetch(`${API_BASE}/policies/sync-active-status`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Sync Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async getStats(): Promise<any> {
    const res = await fetch(`${API_BASE}/stats`);
    if (!res.ok) {
      throw new Error(`Stats Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },
};

