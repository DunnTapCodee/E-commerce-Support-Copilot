import React, { useState } from 'react';
import {
  Send,
  Bot,
  User,
  CheckCircle,
  RefreshCw,
  ShoppingBag,
  Plus,
  Trash2,
  Users,
  MessageSquare,
  Clock,
  Phone,
  Package,
} from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { ChatMessage, GatewayResponse } from '../../types';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';

export interface CustomerProfile {
  id: string;
  name: string;
  phone: string;
  orderId?: string;
  orderStatus?: string;
  orderAmount?: string;
  email?: string;
}

export const MOCK_CUSTOMERS: CustomerProfile[] = [
  {
    id: 'CUST-1100',
    name: 'Lê Văn Sơn',
    phone: '0998.708.581',
    orderId: 'ORD-1100',
    orderStatus: 'Delivered',
    orderAmount: '1.950.000 VNĐ',
    email: 'son.le@gmail.com',
  },
  {
    id: 'CUST-1002',
    name: 'Phan Văn An',
    phone: '0974.716.127',
    orderId: 'ORD-1002',
    orderStatus: 'Shipping',
    orderAmount: '912.000 VNĐ',
    email: 'an.phan@gmail.com',
  },
  {
    id: 'CUST-1001',
    name: 'Bùi Thị An',
    phone: '0938.242.854',
    orderId: 'ORD-1001',
    orderStatus: 'Shipping',
    orderAmount: '1.402.000 VNĐ',
    email: 'an.bui@gmail.com',
  },
  {
    id: 'CUST-1003',
    name: 'Nguyễn Thị Mai',
    phone: '0903.112.233',
    orderId: 'ORD-1003',
    orderStatus: 'Processing',
    orderAmount: '650.000 VNĐ',
    email: 'mai.nguyen@gmail.com',
  },
  {
    id: 'CUST-GUEST',
    name: 'Khách vãng lai (Chưa đăng nhập)',
    phone: 'Chưa cung cấp',
    orderId: undefined,
    orderStatus: undefined,
    orderAmount: undefined,
    email: 'guest@tiki.vn',
  },
];

export interface ConversationSession {
  sessionId: string;
  customerId: string;
  title: string;
  createdAt: string;
  messages: ChatMessage[];
  copilotResponse: GatewayResponse | null;
  editedDraft: string;
}

export const ChatView: React.FC = () => {
  // Selected customer state
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('CUST-1100');

  // Customer sessions map: customerId -> ConversationSession[]
  const [sessionsByCustomer, setSessionsByCustomer] = useState<Record<string, ConversationSession[]>>(() => {
    const initialSessionId = `sess_${Math.random().toString(36).substring(2, 9)}`;
    return {
      'CUST-1100': [
        {
          sessionId: initialSessionId,
          customerId: 'CUST-1100',
          title: 'Tra cứu đơn ORD-1100',
          createdAt: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
          messages: [],
          copilotResponse: null,
          editedDraft: '',
        },
      ],
    };
  });

  // Active session ID
  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    return sessionsByCustomer['CUST-1100']?.[0]?.sessionId || '';
  });

  const [inputQuery, setInputQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Active customer helper
  const currentCustomer =
    MOCK_CUSTOMERS.find((c) => c.id === selectedCustomerId) || MOCK_CUSTOMERS[0];

  // Active session list for selected customer
  const currentSessions = sessionsByCustomer[selectedCustomerId] || [];

  // Active session object
  const activeSession =
    currentSessions.find((s) => s.sessionId === activeSessionId) ||
    currentSessions[0] ||
    null;

  // Handle switching customer from dropdown
  const handleSelectCustomer = (customerId: string) => {
    setSelectedCustomerId(customerId);
    const existing = sessionsByCustomer[customerId] || [];
    if (existing.length > 0) {
      setActiveSessionId(existing[0].sessionId);
    } else {
      // Create new session for this customer
      const newSessId = `sess_${Math.random().toString(36).substring(2, 9)}`;
      const newSession: ConversationSession = {
        sessionId: newSessId,
        customerId: customerId,
        title: 'Hội thoại mới',
        createdAt: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
        messages: [],
        copilotResponse: null,
        editedDraft: '',
      };
      setSessionsByCustomer((prev) => ({
        ...prev,
        [customerId]: [newSession],
      }));
      setActiveSessionId(newSessId);
    }
  };

  // Create new conversation session for current customer
  const handleCreateNewSession = () => {
    const newSessId = `sess_${Math.random().toString(36).substring(2, 9)}`;
    const count = (sessionsByCustomer[selectedCustomerId] || []).length + 1;
    const newSession: ConversationSession = {
      sessionId: newSessId,
      customerId: selectedCustomerId,
      title: `Hội thoại #${count}`,
      createdAt: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
      messages: [],
      copilotResponse: null,
      editedDraft: '',
    };

    setSessionsByCustomer((prev) => ({
      ...prev,
      [selectedCustomerId]: [newSession, ...(prev[selectedCustomerId] || [])],
    }));
    setActiveSessionId(newSessId);
  };

  // Delete a session
  const handleDeleteSession = (sessionIdToDelete: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const remaining = (sessionsByCustomer[selectedCustomerId] || []).filter(
      (s) => s.sessionId !== sessionIdToDelete
    );

    if (remaining.length === 0) {
      // Keep at least one new session
      const newSessId = `sess_${Math.random().toString(36).substring(2, 9)}`;
      const newSession: ConversationSession = {
        sessionId: newSessId,
        customerId: selectedCustomerId,
        title: 'Hội thoại mới',
        createdAt: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
        messages: [],
        copilotResponse: null,
        editedDraft: '',
      };
      setSessionsByCustomer((prev) => ({
        ...prev,
        [selectedCustomerId]: [newSession],
      }));
      setActiveSessionId(newSessId);
    } else {
      setSessionsByCustomer((prev) => ({
        ...prev,
        [selectedCustomerId]: remaining,
      }));
      if (activeSessionId === sessionIdToDelete) {
        setActiveSessionId(remaining[0].sessionId);
      }
    }
  };

  // Send message in active session
  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isLoading || !activeSession) return;

    const userText = inputQuery.trim();
    const currentSessionId = activeSession.sessionId;
    const nowTime = new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });

    const newMsg: ChatMessage = {
      id: Math.random().toString(),
      role: 'customer',
      content: userText,
      timestamp: nowTime,
    };

    // Update session title on first message if generic
    const isFirstMsg = activeSession.messages.length === 0;
    const updatedTitle = isFirstMsg ? (userText.length > 28 ? `${userText.slice(0, 26)}...` : userText) : activeSession.title;

    // Optimistically append user message
    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) => {
          if (s.sessionId === currentSessionId) {
            return {
              ...s,
              title: updatedTitle,
              messages: [...s.messages, newMsg],
            };
          }
          return s;
        }),
      };
    });

    setInputQuery('');
    setIsLoading(true);

    try {
      // Query API Gateway with customer context
      const resp = await apiClient.sendQuery(userText, currentSessionId, currentCustomer.id);

      // Append instant buffer acknowledgement to dialogue if present
      const ackText = resp.customer_acknowledgement;
      const ackMsg: ChatMessage | null = ackText
        ? {
            id: Math.random().toString(),
            role: 'agent',
            content: ackText,
            timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
            isAcknowledgement: true,
          }
        : null;

      setSessionsByCustomer((prev) => {
        const list = prev[selectedCustomerId] || [];
        return {
          ...prev,
          [selectedCustomerId]: list.map((s) => {
            if (s.sessionId === currentSessionId) {
              return {
                ...s,
                messages: ackMsg ? [...s.messages, ackMsg] : s.messages,
                copilotResponse: resp,
                editedDraft: resp.draft_text || '',
              };
            }
            return s;
          }),
        };
      });
    } catch (err: any) {
      alert(`⚠️ Không thể kết nối API Gateway: ${err.message}.\nVui lòng đảm bảo các microservices đã được chạy.`);
    } finally {
      setIsLoading(false);
    }
  };

  // Staff approves draft
  const handleApproveDraft = async () => {
    if (!activeSession || !activeSession.copilotResponse) return;
    const finalContent = activeSession.editedDraft.trim();
    if (!finalContent) return;

    const currentSessionId = activeSession.sessionId;
    const copilotResp = activeSession.copilotResponse;

    const agentMsg: ChatMessage = {
      id: Math.random().toString(),
      role: 'agent',
      content: finalContent,
      timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
      citations: copilotResp.citations,
      isAcknowledgement: false,
    };

    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) => {
          if (s.sessionId === currentSessionId) {
            return {
              ...s,
              messages: [...s.messages, agentMsg],
              copilotResponse: null,
              editedDraft: '',
            };
          }
          return s;
        }),
      };
    });

    try {
      await apiClient.recordAction({
        interaction_id: copilotResp.interaction_id,
        action: finalContent !== copilotResp.draft_text ? 'EDIT' : 'APPROVE',
        final_text: finalContent,
        agent_notes: 'Sent via React TSX frontend after CS review',
        handling_time_ms: 1200,
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleUpdateDraft = (val: string) => {
    if (!activeSession) return;
    const currentSessionId = activeSession.sessionId;
    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) => {
          if (s.sessionId === currentSessionId) {
            return { ...s, editedDraft: val };
          }
          return s;
        }),
      };
    });
  };

  const handleDismissDraft = () => {
    if (!activeSession) return;
    const currentSessionId = activeSession.sessionId;
    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) => {
          if (s.sessionId === currentSessionId) {
            return { ...s, copilotResponse: null, editedDraft: '' };
          }
          return s;
        }),
      };
    });
  };

  const messages = activeSession?.messages || [];
  const copilotResponse = activeSession?.copilotResponse || null;
  const editedDraft = activeSession?.editedDraft || '';

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 h-[calc(100vh-130px)]">
      {/* ------------------------------------------------------------- */}
      {/* COLUMN 1: Customer Selector & Session List (Left ~3 cols)     */}
      {/* ------------------------------------------------------------- */}
      <div className="lg:col-span-3 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {/* Customer Dropdown Header */}
        <div className="p-3.5 border-b border-slate-100 bg-slate-50/70">
          <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5 text-blue-600" />
            <span>Chọn Khách Hàng</span>
          </label>
          <select
            value={selectedCustomerId}
            onChange={(e) => handleSelectCustomer(e.target.value)}
            className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-semibold text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
          >
            {MOCK_CUSTOMERS.map((cust) => (
              <option key={cust.id} value={cust.id}>
                {cust.name} ({cust.phone})
              </option>
            ))}
          </select>

          {/* Quick Customer Mini-Card */}
          <div className="mt-2.5 p-2.5 bg-blue-50/60 rounded-xl border border-blue-100/80 text-[11px] space-y-1">
            <div className="flex justify-between items-center font-semibold text-slate-800">
              <span className="truncate">{currentCustomer.name}</span>
              <span className="text-[10px] font-mono text-blue-600 bg-blue-100/70 px-1.5 py-0.5 rounded">
                {currentCustomer.id}
              </span>
            </div>
            <div className="flex items-center gap-1 text-slate-600">
              <Phone className="w-3 h-3 text-slate-400" />
              <span>{currentCustomer.phone}</span>
            </div>
            {currentCustomer.orderId && (
              <div className="flex items-center justify-between text-slate-600 pt-1 border-t border-blue-100/60">
                <span className="flex items-center gap-1">
                  <Package className="w-3 h-3 text-blue-500" />
                  <b>#{currentCustomer.orderId}</b>
                </span>
                <span className="text-[10px] font-medium text-emerald-700 bg-emerald-100/80 px-1.5 py-0.5 rounded">
                  {currentCustomer.orderStatus}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Sessions Section Header with + New Session */}
        <div className="px-3.5 py-2.5 border-b border-slate-100 flex items-center justify-between">
          <span className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
            <MessageSquare className="w-3.5 h-3.5 text-slate-500" />
            <span>Danh sách phiên</span>
            <span className="text-[11px] text-slate-400 font-normal">({currentSessions.length})</span>
          </span>
          <button
            onClick={handleCreateNewSession}
            className="flex items-center gap-1 px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-600 rounded-lg text-xs font-semibold transition-colors shadow-2xs"
            title="Tạo cuộc hội thoại mới cho khách hàng này"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Mới</span>
          </button>
        </div>

        {/* Session List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {currentSessions.map((s) => {
            const isActive = s.sessionId === activeSessionId;
            const lastMsg = s.messages[s.messages.length - 1];
            return (
              <div
                key={s.sessionId}
                onClick={() => setActiveSessionId(s.sessionId)}
                className={`p-2.5 rounded-xl cursor-pointer transition-all border group relative ${
                  isActive
                    ? 'bg-blue-50/80 border-blue-200 shadow-2xs'
                    : 'bg-white border-transparent hover:bg-slate-50 hover:border-slate-200'
                }`}
              >
                <div className="flex items-start justify-between gap-1">
                  <span
                    className={`text-xs font-semibold truncate ${
                      isActive ? 'text-blue-900' : 'text-slate-700'
                    }`}
                  >
                    {s.title}
                  </span>
                  <button
                    onClick={(e) => handleDeleteSession(s.sessionId, e)}
                    className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 p-0.5 transition-opacity"
                    title="Xóa phiên"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
                <div className="flex items-center justify-between mt-1 text-[11px] text-slate-400">
                  <span className="flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" />
                    <span>{s.createdAt}</span>
                  </span>
                  <span className="bg-slate-100 text-slate-500 px-1.5 py-0.2 rounded text-[10px]">
                    {s.messages.length} tin
                  </span>
                </div>
                {lastMsg && (
                  <p className="text-[11px] text-slate-500 truncate mt-1 italic">
                    {lastMsg.content}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* COLUMN 2: Customer Dialogue Stream (Middle ~5 cols)           */}
      {/* ------------------------------------------------------------- */}
      <div className="lg:col-span-5 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        {/* Chat Header */}
        <div className="p-3.5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center space-x-2">
            <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-bold text-slate-800">{currentCustomer.name}</span>
                <span className="text-[10px] text-slate-400 font-mono">({activeSession?.sessionId})</span>
              </div>
              <span className="text-[11px] text-slate-500">{activeSession?.title}</span>
            </div>
          </div>
          <button
            onClick={() => {
              if (!activeSession) return;
              setSessionsByCustomer((prev) => ({
                ...prev,
                [selectedCustomerId]: prev[selectedCustomerId].map((s) =>
                  s.sessionId === activeSession.sessionId
                    ? { ...s, messages: [], copilotResponse: null, editedDraft: '' }
                    : s
                ),
              }));
            }}
            className="text-xs text-slate-400 hover:text-slate-700 underline"
          >
            Làm sạch tin nhắn
          </button>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 p-8">
              <ShoppingBag className="w-12 h-12 mb-3 text-slate-300 stroke-[1.5]" />
              <p className="text-sm font-semibold text-slate-600">Bắt đầu phiên trò chuyện</p>
              <p className="text-xs mt-1 text-slate-400 max-w-xs">
                Đang hỗ trợ khách hàng <b>{currentCustomer.name}</b>. Nhập câu hỏi để AI Copilot tra cứu đơn hàng và gợi ý bản nháp phản hồi.
              </p>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={`flex gap-3 ${m.role === 'customer' ? 'justify-end' : 'justify-start'}`}
              >
                {m.role === 'agent' && (
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm ${
                      m.isAcknowledgement ? 'bg-amber-100 text-amber-600' : 'bg-emerald-100 text-emerald-700'
                    }`}
                  >
                    {m.isAcknowledgement ? <Bot className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                  </div>
                )}
                <div
                  className={`max-w-[82%] rounded-2xl p-3.5 text-xs whitespace-pre-wrap leading-relaxed ${
                    m.role === 'customer'
                      ? 'bg-blue-600 text-white rounded-tr-sm'
                      : m.isAcknowledgement
                        ? 'bg-amber-50/90 text-amber-950 border border-amber-200/60 rounded-tl-sm'
                        : 'bg-slate-100 text-slate-800 rounded-tl-sm border border-slate-200/60'
                  }`}
                >
                  {m.isAcknowledgement && (
                    <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-700 mb-1.5 pb-1 border-b border-amber-200/50">
                      <span>⚡ Phản hồi đệm tức thì (Copilot)</span>
                    </div>
                  )}
                  {!m.isAcknowledgement && m.role === 'agent' && (
                    <div className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 mb-1.5 pb-1 border-b border-slate-200">
                      <span>👤 Nhân viên CSKH (Đã duyệt)</span>
                    </div>
                  )}
                  <p>{m.content}</p>
                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-2.5 pt-2 border-t border-slate-200/60 text-[11px] text-slate-500">
                      <span className="font-semibold">📚 Căn cứ chính sách:</span>{' '}
                      {m.citations.map((c) => `[${c.doc_id}] ${c.title}`).join(', ')}
                    </div>
                  )}
                  <span
                    className={`block text-[10px] mt-1.5 text-right ${
                      m.role === 'customer'
                        ? 'text-blue-200'
                        : m.isAcknowledgement
                          ? 'text-amber-600/70'
                          : 'text-slate-400'
                    }`}
                  >
                    {m.timestamp}
                  </span>
                </div>
                {m.role === 'customer' && (
                  <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center flex-shrink-0 text-sm">
                    <User className="w-4 h-4" />
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Input Field */}
        <form onSubmit={handleSend} className="p-3 border-t border-slate-100 bg-white flex gap-2">
          <input
            type="text"
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            placeholder={`Nhập câu hỏi từ khách hàng ${currentCustomer.name}...`}
            disabled={isLoading || !activeSession}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 disabled:bg-slate-50"
          />
          <button
            type="submit"
            disabled={isLoading || !inputQuery.trim() || !activeSession}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1.5 cursor-pointer shadow-sm"
          >
            {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            <span>Gửi</span>
          </button>
        </form>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* COLUMN 3: Copilot CS Support & Draft Editor (Right ~4 cols)   */}
      {/* ------------------------------------------------------------- */}
      <div className="lg:col-span-4 flex flex-col space-y-4 overflow-y-auto">
        {copilotResponse ? (
          <>
            {/* Guardrail & Classification Analysis Card */}
            <Card title="🛡️ Phân tích Thông minh từ Copilot">
              <div className="space-y-2.5 text-xs">
                <div className="flex items-center justify-between pb-1.5 border-b border-slate-100">
                  <span className="text-slate-500">Ý định dự đoán:</span>
                  <div className="flex items-center gap-1.5">
                    <Badge variant="info">{copilotResponse.intent?.intent}</Badge>
                    <span className="text-slate-400 font-mono">
                      ({Math.round((copilotResponse.intent?.confidence || 0) * 100)}%)
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between pb-1.5 border-b border-slate-100">
                  <span className="text-slate-500">Loại input:</span>
                  <span className="font-semibold text-slate-700">{copilotResponse.input_type || 'N/A'}</span>
                </div>

                <div className="flex items-start justify-between pb-1.5 border-b border-slate-100">
                  <span className="text-slate-500">Chốt chặn Guardrail:</span>
                  <Badge
                    variant={
                      copilotResponse.guardrail?.action_type === 'PROCEED_TO_LLM'
                        ? 'success'
                        : copilotResponse.guardrail?.action_type === 'DIRECT_REFUND_FORM'
                          ? 'warning'
                          : 'danger'
                    }
                  >
                    {copilotResponse.guardrail?.action_type}
                  </Badge>
                </div>

                <p className="text-slate-600 italic bg-slate-50 p-2.5 rounded-lg border border-slate-100 text-[11px]">
                  "{copilotResponse.guardrail?.reason}"
                </p>
              </div>
            </Card>

            {/* Dynamic Order Card (Module 3) */}
            {copilotResponse.order_data && (
              <Card title="📦 Tra cứu Đơn hàng (Dynamic Tool Calling)">
                <div className="p-3 bg-blue-50/50 rounded-xl border border-blue-100 text-xs space-y-1.5">
                  <div className="flex justify-between font-semibold text-slate-800">
                    <span>Mã đơn: #{copilotResponse.order_data.order_id}</span>
                    <Badge variant="info">{copilotResponse.order_data.status}</Badge>
                  </div>
                  <p className="text-slate-600">
                    Khách: {copilotResponse.order_data.customer_name} ({copilotResponse.order_data.phone})
                  </p>
                  <p className="text-slate-600">
                    Sản phẩm: {copilotResponse.order_data.items?.map((it: any) => it.name).join(', ')}
                  </p>
                  <p className="text-slate-600 font-semibold">
                    Tổng tiền: {copilotResponse.order_data.total_amount?.toLocaleString('vi-VN')} VND
                  </p>
                  <p className="text-slate-500">
                    Giao hàng: {copilotResponse.order_data.estimated_delivery} ({copilotResponse.order_data.carrier})
                  </p>
                </div>
              </Card>
            )}

            {/* CS Draft Response Editor */}
            <Card title="✍️ Bản nháp Đề xuất cho Nhân viên">
              {copilotResponse.customer_acknowledgement && (
                <div className="mb-2.5 p-2 bg-amber-50 rounded-lg border border-amber-100 text-[11px] text-amber-800">
                  <span className="font-semibold block mb-0.5">⚡ Câu đệm đã gửi tự động:</span>
                  <i>"{copilotResponse.customer_acknowledgement}"</i>
                </div>
              )}

              <textarea
                value={editedDraft}
                onChange={(e) => handleUpdateDraft(e.target.value)}
                rows={5}
                className="w-full p-2.5 rounded-xl border border-slate-200 text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-sans"
              />

              <div className="mt-3 flex gap-2">
                <button
                  onClick={handleApproveDraft}
                  className="flex-1 py-2 px-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors shadow-sm cursor-pointer"
                >
                  <CheckCircle className="w-4 h-4" />
                  <span>Duyệt & Gửi Khách</span>
                </button>
                <button
                  onClick={handleDismissDraft}
                  className="py-2 px-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition-colors cursor-pointer"
                >
                  Bỏ qua
                </button>
              </div>
            </Card>

            {/* Citations List */}
            {copilotResponse.citations && copilotResponse.citations.length > 0 && (
              <Card title="📚 Căn cứ Chính sách Trích xuất">
                <div className="space-y-2 text-xs">
                  {copilotResponse.citations.map((c) => (
                    <div key={c.doc_id} className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                      <div className="flex justify-between font-semibold text-slate-800 mb-1">
                        <span>[{c.doc_id}] {c.title}</span>
                        <Badge variant={c.is_active ? 'success' : 'danger'}>
                          {c.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </div>
                      <p className="text-slate-600 line-clamp-3 text-[11px]">{c.content}</p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 bg-white rounded-2xl border border-slate-200 text-slate-400">
            <Bot className="w-12 h-12 mb-3 text-slate-300 stroke-[1.5]" />
            <p className="text-sm font-semibold text-slate-700">Khung làm việc Copilot</p>
            <p className="text-xs mt-1 text-slate-400 max-w-xs">
              Khi khách hàng gửi câu hỏi, AI Copilot sẽ tự động phân tích ý định, kiểm tra chốt chặn an toàn và soạn sẵn câu trả lời tối ưu tại đây để nhân viên CSKH duyệt.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
