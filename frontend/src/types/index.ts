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
  all_probabilities?: Record<string, number>;
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
  is_hard_fail?: boolean;
  violations?: string[];
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
  retrieval_status?: string;
  circuit_breaker_tripped?: boolean;
  components_used?: Record<string, string>;
  rewritten_query?: string;
  customer_question?: string;
  pending_action?: OrderActionProposal | null;
}

export type OrderActionType = 'cancel_order' | 'update_address' | 'update_receiver' | 'return_product';

export interface OrderActionProposal {
  action_id: string;
  interaction_id?: string | null;
  session_id?: string | null;
  order_id: string;
  customer_id: string;
  action_type: OrderActionType;
  before_values: Record<string, any>;
  proposed_values: Record<string, any>;
  eligible: boolean;
  ineligibility_reason?: string | null;
  customer_reason?: string | null;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  decision_reason?: string | null;
  performed_by?: string | null;
  created_at?: string | null;
  decided_at?: string | null;
}

export interface DelayNotificationRecord {
  order_id: string;
  customer_id: string;
  customer_name?: string | null;
  promised_delivery_date: string;
  days_overdue: number;
  voucher_code: string;
  voucher_amount: number;
  message_text: string;
  status: 'PENDING_SEND' | 'SENT';
  created_at?: string | null;
  sent_at?: string | null;
}

export interface IncidentClusterSummary {
  cluster_id: string;
  predicted_intent: string;
  issue_topic: string;
  count: number;
  is_widespread: boolean;
  sample_queries: string[];
  suggested_broadcast: string;
  latest_timestamp?: string | null;
}

export interface PendingDraftItem {
  interactionId: string;
  customerQuestion: string;
  copilotDraft: string;
  copilotResponse: GatewayResponse | null;
  createdAt?: string;
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
  role: 'customer' | 'agent' | 'system' | 'acknowledgement';
  content: string;
  timestamp: string;
  citations?: RetrievedDocument[];
  isAcknowledgement?: boolean;
}

export interface CustomerOrderRecord {
  order_id: string;
  customer_id?: string;
  customer_name?: string;
  phone?: string;
  product_name?: string;
  items?: Array<{ name: string; quantity?: number; price?: number }>;
  total_amount?: number;
  order_status?: string;
  payment_method?: string;
  payment_status?: string;
  carrier?: string;
  tracking_code?: string;
  estimated_delivery?: string;
  created_at?: string;
}

export interface StaffProfile {
  staff_id: string;
  name: string;
  email: string;
  role: string;
  department: string;
  created_at?: string;
}

export interface CustomerProfileRecord {
  customer_id: string;
  name: string;
  phone?: string;
  email?: string;
  assigned_staff_id?: string;
  assigned_staff_name?: string;
  created_at?: string;
}

export interface CustomerOverviewResponse {
  customer: CustomerProfileRecord;
  orders: Array<Record<string, any>>;
  total_orders: number;
  chat_sessions: Array<{
    sessionId: string;
    customerId: string;
    title: string;
    createdAt: string;
    updatedAt: string;
    messageCount: number;
  }>;
}


