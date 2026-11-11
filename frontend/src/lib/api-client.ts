import {
  GatewayResponse,
  PolicyAuditLogEntry,
  PolicyFilterResult,
  RetrievedDocument,
} from '../types';

const API_BASE = '/api/v1/copilot';

export const apiClient = {
  // Fast Buffer Acknowledgement (< 50ms)
  async getFastAck(query: string, sessionId: string, customerId?: string): Promise<{ customer_acknowledgement: string; intent: string }> {
    try {
      const res = await fetch(`${API_BASE}/fast_ack`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, session_id: sessionId, customer_id: customerId }),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.warn('Fast ack fetch error, using local fallback:', err);
    }
    return {
      customer_acknowledgement: 'Dạ em đã ghi nhận thông tin của anh/chị và đang kiểm tra hỗ trợ ngay đây ạ! Quý khách đợi em trong giây lát nhé.',
      intent: 'general_inquiry',
    };
  },

  // Persistent Session & Turn Management in SQLite
  async listSessions(customerId?: string): Promise<Array<{ sessionId: string; customerId: string; title: string; createdAt: string; updatedAt: string; messageCount: number }>> {
    try {
      const url = customerId ? `${API_BASE}/sessions?customer_id=${customerId}` : `${API_BASE}/sessions`;
      const res = await fetch(url);
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.warn('List sessions error:', err);
    }
    return [];
  },

  async getSessionDetails(sessionId: string): Promise<any | null> {
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/details`);
      if (res.ok) {
        return await res.json();
      }
    } catch (err) {
      console.warn('Get session details error:', err);
    }
    return null;
  },

  async createSession(sessionId: string, customerId: string, title?: string): Promise<void> {
    try {
      await fetch(`${API_BASE}/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, customer_id: customerId, title: title || 'Hội thoại mới' }),
      });
    } catch (err) {
      console.warn('Create session error:', err);
    }
  },

  async deleteSession(sessionId: string): Promise<void> {
    try {
      await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' });
    } catch (err) {
      console.warn('Delete session error:', err);
    }
  },

  async updateSessionTitle(sessionId: string, title: string): Promise<void> {
    try {
      await fetch(`${API_BASE}/session/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      });
    } catch (err) {
      console.warn('Update session title error:', err);
    }
  },

  async saveMessage(sessionId: string, role: string, content: string, isAcknowledgement?: boolean): Promise<void> {
    try {
      await fetch(`${API_BASE}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          role,
          content,
          is_acknowledgement: Boolean(isAcknowledgement),
        }),
      });
    } catch (err) {
      console.warn('Save message error:', err);
    }
  },

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

  async queryCopilotStream(
    query: string,
    sessionId: string,
    customerId: string | undefined,
    callbacks: {
      onMeta?: (meta: any) => void;
      onToken?: (token: string) => void;
      onDone?: (data: { draft_text: string; interaction_id?: string }) => void;
      onError?: (err: any) => void;
    }
  ): Promise<void> {
    try {
      const res = await fetch(`${API_BASE}/query_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          session_id: sessionId,
          customer_id: customerId,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`Stream Error (${res.status}): ${await res.text()}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('event:')) {
            currentEvent = trimmed.slice(6).trim();
          } else if (trimmed.startsWith('data:')) {
            const dataStr = trimmed.slice(5).trim();
            if (!dataStr) continue;
            try {
              const parsed = JSON.parse(dataStr);
              if (currentEvent === 'meta' || parsed.type === 'meta') {
                callbacks.onMeta?.(parsed);
              } else if (currentEvent === 'token' || parsed.type === 'token') {
                callbacks.onToken?.(parsed.delta || '');
              } else if (currentEvent === 'done' || parsed.type === 'done') {
                callbacks.onDone?.(parsed);
              }
            } catch (jsonErr) {
              console.warn('SSE JSON parse error:', jsonErr, dataStr);
            }
          }
        }
      }
    } catch (err) {
      if (callbacks.onError) {
        callbacks.onError(err);
      } else {
        throw err;
      }
    }
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

  async filterPolicyBulk(rawText: string, suggestedCategory?: string): Promise<PolicyFilterResult[]> {
    const res = await fetch(`${API_BASE}/policy/filter-bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_text: rawText,
        suggested_category: suggestedCategory,
      }),
    });
    if (!res.ok) {
      throw new Error(`Bulk Filter Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async parseDocumentFile(file: File): Promise<{ filename: string; text: string; size: number }> {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/policy/parse-file`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      throw new Error(`Parse File Error (${res.status}): ${await res.text()}`);
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

  async getEvaluationSummary(): Promise<any> {
    const res = await fetch(`${API_BASE}/evaluation/summary`);
    if (!res.ok) {
      throw new Error(`Evaluation Summary Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },

  async runLiveEvaluation(): Promise<any> {
    const res = await fetch(`${API_BASE}/evaluation/run`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Run Evaluation Error (${res.status}): ${await res.text()}`);
    }
    return res.json();
  },
};

