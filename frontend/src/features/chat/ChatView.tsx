import React, { useState } from 'react';
import { Send, Bot, User, CheckCircle, RefreshCw, XCircle, ShieldAlert, Package, ShoppingBag } from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { ChatMessage, GatewayResponse } from '../../types';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';

export const ChatView: React.FC = () => {
  const [sessionId] = useState(() => `sess_${Math.random().toString(36).substring(2, 9)}`);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copilotResponse, setCopilotResponse] = useState<GatewayResponse | null>(null);
  const [editedDraft, setEditedDraft] = useState('');

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isLoading) return;

    const userText = inputQuery.trim();
    const newMsg: ChatMessage = {
      id: Math.random().toString(),
      role: 'customer',
      content: userText,
      timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, newMsg]);
    setInputQuery('');
    setIsLoading(true);

    try {
      const resp = await apiClient.sendQuery(userText, sessionId);
      setCopilotResponse(resp);
      setEditedDraft(resp.draft_text || '');

      // Deliver ONLY the instant buffer acknowledgement to customer dialogue
      // The official draft is held in the right panel for CS Agent approval
      const ackText = resp.customer_acknowledgement;
      if (ackText) {
        setMessages((prev) => [
          ...prev,
          {
            id: Math.random().toString(),
            role: 'agent',
            content: ackText,
            timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
            isAcknowledgement: true,
          },
        ]);
      }
    } catch (err: any) {
      alert(`⚠️ Không thể kết nối API Gateway: ${err.message}.\nVui lòng đảm bảo các backend microservices đã chạy (python run_dev.py).`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleApproveDraft = async () => {
    if (!copilotResponse) return;
    const finalContent = editedDraft.trim();
    if (!finalContent) return;

    const agentMsg: ChatMessage = {
      id: Math.random().toString(),
      role: 'agent',
      content: finalContent,
      timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
      citations: copilotResponse.citations,
      isAcknowledgement: false,
    };

    setMessages((prev) => [...prev, agentMsg]);

    try {
      await apiClient.recordAction({
        interaction_id: copilotResponse.interaction_id,
        action: editedDraft !== copilotResponse.draft_text ? 'EDIT' : 'APPROVE',
        final_text: finalContent,
        agent_notes: 'Sent via React TSX frontend after CS review',
        handling_time_ms: 1200,
      });
    } catch (err) {
      console.error(err);
    }

    setCopilotResponse(null);
    setEditedDraft('');
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-140px)]">
      {/* Customer Dialogue Panel (Left) */}
      <div className="lg:col-span-7 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center space-x-2">
            <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></div>
            <span className="text-sm font-semibold text-slate-700">Hội thoại Khách hàng</span>
            <span className="text-xs text-slate-400 font-mono">({sessionId})</span>
          </div>
          <button
            onClick={() => {
              setMessages([]);
              setCopilotResponse(null);
            }}
            className="text-xs text-slate-500 hover:text-slate-800 underline"
          >
            Làm mới hội thoại
          </button>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 p-8">
              <ShoppingBag className="w-12 h-12 mb-3 text-slate-300 stroke-[1.5]" />
              <p className="text-sm font-medium">Chưa có tin nhắn trong phiên này</p>
              <p className="text-xs mt-1 text-slate-400">
                Thử nhập câu hỏi như: <i>"Kiểm tra giúp mình đơn hàng ORD-2024-001 với"</i> hoặc <i>"Chính sách đổi trả sản phẩm thế nào?"</i>
              </p>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={`flex gap-3 ${m.role === 'customer' ? 'justify-end' : 'justify-start'}`}
              >
                {m.role === 'agent' && (
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm ${
                    m.isAcknowledgement ? 'bg-amber-100 text-amber-600' : 'bg-emerald-100 text-emerald-700'
                  }`}>
                    {m.isAcknowledgement ? <Bot className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-2xl p-4 text-sm whitespace-pre-wrap leading-relaxed ${
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
                    <div className="mt-3 pt-2 border-t border-slate-200/60 text-xs text-slate-500">
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
            placeholder="Nhập tin nhắn khách hàng..."
            disabled={isLoading}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 disabled:bg-slate-50"
          />
          <button
            type="submit"
            disabled={isLoading || !inputQuery.trim()}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            <span>Gửi</span>
          </button>
        </form>
      </div>

      {/* Copilot Assistant & Draft Editor Panel (Right) */}
      <div className="lg:col-span-5 flex flex-col space-y-4 overflow-y-auto">
        {copilotResponse ? (
          <>
            {/* Guardrail & Classification Analysis Card */}
            <Card title="🛡️ Phân tích Thông minh từ Copilot">
              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <span className="text-slate-500">Ý định dự đoán:</span>
                  <div className="flex items-center gap-1.5">
                    <Badge variant="info">{copilotResponse.intent?.intent}</Badge>
                    <span className="text-slate-400 font-mono">
                      ({Math.round((copilotResponse.intent?.confidence || 0) * 100)}%)
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <span className="text-slate-500">Loại input:</span>
                  <span className="font-semibold text-slate-700">{copilotResponse.input_type || 'N/A'}</span>
                </div>

                <div className="flex items-start justify-between pb-2 border-b border-slate-100">
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

                <p className="text-slate-600 italic bg-slate-50 p-2.5 rounded-lg border border-slate-100">
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
                <div className="mb-3 p-2.5 bg-amber-50 rounded-lg border border-amber-100 text-xs text-amber-800">
                  <span className="font-semibold block mb-0.5">Phần 1: Lời đệm tức thì gửi khách:</span>
                  <i>"{copilotResponse.customer_acknowledgement}"</i>
                </div>
              )}

              <textarea
                value={editedDraft}
                onChange={(e) => setEditedDraft(e.target.value)}
                rows={5}
                className="w-full p-3 rounded-xl border border-slate-200 text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-sans"
              />

              <div className="mt-4 flex gap-2">
                <button
                  onClick={handleApproveDraft}
                  className="flex-1 py-2 px-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                >
                  <CheckCircle className="w-4 h-4" />
                  <span>Duyệt & Gửi Khách</span>
                </button>
                <button
                  onClick={() => setCopilotResponse(null)}
                  className="py-2 px-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition-colors"
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
                      <p className="text-slate-600 line-clamp-3">{c.content}</p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 bg-white rounded-2xl border border-slate-200 text-slate-400">
            <Bot className="w-12 h-12 mb-3 text-slate-300 stroke-[1.5]" />
            <p className="text-sm font-medium">Khung phân tích Copilot</p>
            <p className="text-xs mt-1 text-slate-400">
              Gửi một câu hỏi từ phía khách hàng để xem phân tích ý định, thẻ đơn hàng động và bản nháp phản hồi.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

