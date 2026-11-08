export interface RetrievedDocument {
  doc_id: string;
  category?: string;
  title: string;
  content: string;
  version: string;
  is_active: boolean;
  policy_type: 'permanent' | 'temporary' | 'superseded';
  effective_date?: string | null;
  expiration_date?: string | null;
  tags: string[];
  score?: number;
}

export interface IntentPredictionResponse {
  intent: string;
  confidence: number;
  is_in_scope: boolean;
  language?: string;
  model_name?: string;
  latency_ms?: number;
}

export interface GuardrailResult {
  allow_llm: boolean;
  action_type: string;
  reason: string;
  faithfulness_score?: number;
  hallucination_detected?: boolean;
  temporal_status?: string;
}

export interface GatewayResponse {
  interaction_id: string;
  intent: IntentPredictionResponse;
  guardrail: GuardrailResult;
  citations: RetrievedDocument[];
  draft_text: string;
  order_data?: Record<string, any> | null;
  tool_calls: Array<Record<string, any>>;
  generation_mode: string;
  suggested_reply?: string;
  agent_guidance?: string;
  input_type?: string;
  active_facts: Record<string, any>;
  is_live_chat: boolean;
  customer_acknowledgement?: string;
  session_turns?: Array<Record<string, any>>;
  context_summary?: string;
  components_used?: Record<string, string>;
  rewritten_query?: string;
}

export interface PolicyAuditLogEntry {
  log_id: string;
  timestamp: string;
  doc_id: string;
  doc_title?: string;
  action: 'CREATE' | 'UPDATE' | 'SUPERSEDE' | 'AUTO_EXPIRE' | 'AUTO_ACTIVATE' | 'ROLLBACK' | 'DELETE';
  performed_by: string;
  reason?: string;
  before_snapshot?: Record<string, any> | null;
  after_snapshot?: Record<string, any> | null;
}

export interface PolicyFilterResult {
  extracted_policy: RetrievedDocument;
  warnings: string[];
  confidence_score: number;
}

export interface ChatMessage {
  id: string;
  role: 'customer' | 'agent' | 'system';
  content: string;
  timestamp: string;
  citations?: RetrievedDocument[];
  isAcknowledgement?: boolean;
}

