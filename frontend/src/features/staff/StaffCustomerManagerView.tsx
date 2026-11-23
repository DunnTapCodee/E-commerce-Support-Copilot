import React, { useEffect, useState } from 'react';
import {
  User,
  Phone,
  Mail,
  ShoppingBag,
  MessageSquare,
  Search,
  Send,
  Package,
  CreditCard,
  Truck,
  RefreshCw,
  CheckCircle2,
  Clock,
  Bot,
  CornerUpLeft,
} from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { ChatMessage, CustomerProfileRecord } from '../../types';
import { formatSystemTime } from '../../lib/time';

interface StaffCustomerManagerViewProps {
  selectedStaffId: string;
  selectedStaffName: string;
  onOpenInCopilot?: (customerId: string, sessionId?: string) => void;
}

type DetailSubTab = 'orders' | 'chats';

export const StaffCustomerManagerView: React.FC<StaffCustomerManagerViewProps> = ({
  selectedStaffId,
  selectedStaffName,
  onOpenInCopilot,
}) => {
  const [customers, setCustomers] = useState<CustomerProfileRecord[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');
  const [searchText, setSearchText] = useState('');
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(false);

  // Customer Detail State
  const [subTab, setSubTab] = useState<DetailSubTab>('orders');
  const [orders, setOrders] = useState<Array<Record<string, any>>>([]);
  const [sessions, setSessions] = useState<
    Array<{
      sessionId: string;
      customerId: string;
      title: string;
      createdAt: string;
      updatedAt: string;
      messageCount: number;
    }>
  >([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');
  const [sessionMessages, setSessionMessages] = useState<ChatMessage[]>([]);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  // Staff direct reply input
  const [staffReplyText, setStaffReplyText] = useState('');
  const [isSendingReply, setIsSendingReply] = useState(false);

  // Activity map across all customers to sort newest questions to top
  const [customerActivity, setCustomerActivity] = useState<
    Record<string, { updatedAt: string; hasPendingDraft: boolean; lastTitle: string }>
  >({});

  const refreshCustomerActivity = async () => {
    try {
      const allSess = await apiClient.listSessions();
      if (!Array.isArray(allSess)) return;
      const map: Record<string, { updatedAt: string; hasPendingDraft: boolean; lastTitle: string }> = {};
      for (const s of allSess) {
        const cid = s.customerId;
        if (!cid) continue;
        const updatedAt = s.updatedAt || s.createdAt || '';
        const hasDraft = Boolean(s.copilotDraft && String(s.copilotDraft).trim());
        const existing = map[cid];
        if (!existing) {
          map[cid] = {
            updatedAt,
            hasPendingDraft: hasDraft,
            lastTitle: s.title || 'Hội thoại mới',
          };
        } else {
          if (updatedAt > existing.updatedAt) {
            existing.updatedAt = updatedAt;
            existing.lastTitle = s.title || existing.lastTitle;
          }
          if (hasDraft) {
            existing.hasPendingDraft = true;
            existing.lastTitle = s.title || existing.lastTitle;
          }
        }
      }
      setCustomerActivity(map);
    } catch (e) {
      // ignore
    }
  };

  // 1. Load customers assigned to selectedStaffId
  const fetchAssignedCustomers = async () => {
    if (!selectedStaffId) return;
    setIsLoadingCustomers(true);
    const [list] = await Promise.all([
      apiClient.listCustomers(selectedStaffId),
      refreshCustomerActivity(),
    ]);
    setCustomers(list);
    if (list.length > 0) {
      setSelectedCustomerId((prev) => (list.some((c) => c.customer_id === prev) ? prev : list[0].customer_id));
    } else {
      setSelectedCustomerId('');
    }
    setIsLoadingCustomers(false);
  };

  useEffect(() => {
    fetchAssignedCustomers();
  }, [selectedStaffId]);

  // 2. Load selected customer overview (orders + chat sessions)
  const fetchCustomerOverview = async (customerId: string) => {
    if (!customerId) return;
    setIsLoadingDetail(true);
    const overview = await apiClient.getCustomerOverview(customerId);
    if (overview) {
      setOrders(overview.orders || []);
      const chatList = overview.chat_sessions || [];
      setSessions(chatList);
      if (chatList.length > 0) {
        setActiveSessionId(chatList[0].sessionId);
      } else {
        setActiveSessionId('');
        setSessionMessages([]);
      }
    } else {
      const ord = await apiClient.getCustomerOrders(customerId);
      const sess = await apiClient.listSessions(customerId);
      setOrders(ord);
      setSessions(sess);
      setActiveSessionId(sess[0]?.sessionId || '');
    }
    setIsLoadingDetail(false);
  };

  useEffect(() => {
    if (selectedCustomerId) {
      fetchCustomerOverview(selectedCustomerId);
    } else {
      setOrders([]);
      setSessions([]);
      setSessionMessages([]);
    }
  }, [selectedCustomerId]);

  // 3. Load messages of activeSessionId (with 3s real-time sync)
  useEffect(() => {
    if (!activeSessionId) {
      setSessionMessages([]);
      return;
    }
    let mounted = true;
    const loadSessionMessages = async () => {
      const details = await apiClient.getSessionDetails(activeSessionId);
      if (mounted && details && Array.isArray(details.messages)) {
        setSessionMessages(details.messages);
      } else if (mounted) {
        setSessionMessages([]);
      }
    };
    loadSessionMessages();
    const timer = setInterval(loadSessionMessages, 3000);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [activeSessionId]);

  const handleSendStaffIntervention = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = staffReplyText.trim();
    if (!content || !activeSessionId || isSendingReply) return;

    setIsSendingReply(true);
    const formattedContent = `[Nhân viên ${selectedStaffName}]: ${content}`;
    const newMsg: ChatMessage = {
      id: `staff_${Date.now()}`,
      role: 'agent',
      content: formattedContent,
      timestamp: formatSystemTime(),
    };

    setSessionMessages((prev) => [...prev, newMsg]);
    setStaffReplyText('');
    await apiClient.saveMessage(activeSessionId, 'agent', formattedContent, false);
    setIsSendingReply(false);
  };

  const filteredCustomers = React.useMemo(() => {
    const base = customers.filter((c) => {
      const q = searchText.toLowerCase();
      return (
        c.name.toLowerCase().includes(q) ||
        c.customer_id.toLowerCase().includes(q) ||
        (c.phone || '').toLowerCase().includes(q) ||
        (c.email || '').toLowerCase().includes(q)
      );
    });
    return [...base].sort((a, b) => {
      const actA = customerActivity[a.customer_id];
      const actB = customerActivity[b.customer_id];
      if (actA?.hasPendingDraft && !actB?.hasPendingDraft) return -1;
      if (!actA?.hasPendingDraft && actB?.hasPendingDraft) return 1;
      const timeA = actA?.updatedAt ? new Date(actA.updatedAt).getTime() : 0;
      const timeB = actB?.updatedAt ? new Date(actB.updatedAt).getTime() : 0;
      return timeB - timeA;
    });
  }, [customers, searchText, customerActivity]);

  const activeCustomer = customers.find((c) => c.customer_id === selectedCustomerId);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-[calc(100vh-6.5rem)]">
      {/* LEFT COLUMN: Assigned Customers List */}
      <aside className="lg:col-span-4 xl:col-span-3 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
        <div className="p-4 border-b border-slate-100 bg-gradient-to-r from-indigo-50/70 to-blue-50/40">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-bold text-slate-800">Khách hàng phụ trách</h2>
            <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-indigo-100 text-indigo-700">
              {customers.length} KH
            </span>
          </div>
          <p className="text-[11px] text-slate-500">
            Nhân viên: <span className="font-semibold text-slate-700">{selectedStaffName}</span> ({selectedStaffId})
          </p>

          {/* Search box */}
          <div className="mt-3 relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Tìm tên, mã KH, SĐT..."
              className="w-full pl-8 pr-3 py-1.5 rounded-xl border border-slate-200 bg-white text-xs focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto overscroll-contain p-2 space-y-1.5">
          {isLoadingCustomers ? (
            <div className="p-6 text-center text-xs text-slate-400">Đang tải danh sách khách hàng...</div>
          ) : filteredCustomers.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-400">
              Không có khách hàng nào thuộc nhân viên này.
            </div>
          ) : (
            filteredCustomers.map((c, idx) => {
              const isSelected = c.customer_id === selectedCustomerId;
              const act = customerActivity[c.customer_id];
              return (
                <div
                  key={c.customer_id}
                  onClick={() => setSelectedCustomerId(c.customer_id)}
                  className={`p-3 rounded-xl cursor-pointer transition-all border ${
                    isSelected
                      ? 'bg-indigo-50/80 border-indigo-300 shadow-sm'
                      : act?.hasPendingDraft
                        ? 'bg-amber-50/80 hover:bg-amber-100/70 border-amber-300'
                        : 'bg-white hover:bg-slate-50 border-slate-100'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1 gap-1">
                    <div className="flex items-center gap-1 min-w-0">
                      {idx === 0 && act?.updatedAt && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-extrabold shrink-0">
                          MỚI NHẤT
                        </span>
                      )}
                      <span className="text-xs font-bold text-slate-900 truncate">{c.name}</span>
                    </div>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 shrink-0">
                      {c.customer_id}
                    </span>
                  </div>
                  {act?.lastTitle && (
                    <p className="text-[11px] text-slate-600 truncate mb-1">
                      💬 {act.lastTitle}
                    </p>
                  )}
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span className="flex items-center gap-1">
                      <Phone className="w-3 h-3 text-slate-400" />
                      {c.phone || 'Chưa có SĐT'}
                    </span>
                    {act?.hasPendingDraft ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-800 bg-amber-100 border border-amber-300 px-2 py-0.5 rounded-full animate-pulse">
                        ⏳ Chờ trả lời
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
                        <CheckCircle2 className="w-2.5 h-2.5" />
                        Đang hoạt động
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* RIGHT COLUMN: Customer Detail (Orders & Chat History) */}
      <section className="lg:col-span-8 xl:col-span-9 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
        {!activeCustomer ? (
          <div className="flex-1 flex items-center justify-center text-xs text-slate-400 p-8">
            Chọn một khách hàng ở cột bên trái để xem hồ sơ chi tiết.
          </div>
        ) : (
          <>
            {/* Customer Profile Header */}
            <div className="p-4 sm:p-5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-50/60">
              <div className="flex items-center gap-3.5">
                <div className="w-11 h-11 rounded-2xl bg-indigo-600 text-white flex items-center justify-center font-bold text-sm shadow-sm">
                  <User className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-slate-900">{activeCustomer.name}</h3>
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-700">
                      {activeCustomer.customer_id}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-3 mt-1 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <Phone className="w-3.5 h-3.5 text-slate-400" />
                      {activeCustomer.phone || 'N/A'}
                    </span>
                    <span className="flex items-center gap-1">
                      <Mail className="w-3.5 h-3.5 text-slate-400" />
                      {activeCustomer.email || 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Sub-tab Switcher + Open in Copilot button */}
              <div className="flex flex-wrap items-center gap-2">
                {onOpenInCopilot && (
                  <button
                    type="button"
                    onClick={() => onOpenInCopilot(activeCustomer.customer_id, activeSessionId || undefined)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
                    title="Chuyển sang Bàn làm việc AI Copilot để hỗ trợ khách hàng này"
                  >
                    <Bot className="w-3.5 h-3.5" />
                    <span>Hỗ trợ với AI Copilot</span>
                  </button>
                )}

                <div className="flex bg-slate-200/70 p-1 rounded-xl">
                  <button
                    type="button"
                    onClick={() => setSubTab('orders')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      subTab === 'orders' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <ShoppingBag className="w-3.5 h-3.5" />
                    <span>Đơn hàng & Giao dịch ({orders.length})</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSubTab('chats')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      subTab === 'chats' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <MessageSquare className="w-3.5 h-3.5" />
                    <span>Lịch sử Phiên chat ({sessions.length})</span>
                  </button>
                </div>

                <button
                  type="button"
                  onClick={() => fetchCustomerOverview(selectedCustomerId)}
                  className="p-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-100 text-slate-600"
                  title="Làm mới dữ liệu khách hàng"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Sub-tab 1: Orders & Transactions */}
            {subTab === 'orders' && (
              <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
                {isLoadingDetail ? (
                  <div className="p-8 text-center text-xs text-slate-400">Đang tải lịch sử đơn hàng...</div>
                ) : orders.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-400">
                    Khách hàng này chưa có đơn hàng nào được ghi nhận.
                  </div>
                ) : (
                  <div className="overflow-x-auto border border-slate-200 rounded-2xl">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold">
                        <tr>
                          <th className="px-4 py-3">Mã đơn</th>
                          <th className="px-4 py-3">Sản phẩm</th>
                          <th className="px-4 py-3">Tổng tiền & Thanh toán</th>
                          <th className="px-4 py-3">Vận chuyển</th>
                          <th className="px-4 py-3">Trạng thái</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {orders.map((ord) => {
                          const items = Array.isArray(ord.items) ? ord.items : [];
                          const productNames =
                            items.map((i: any) => `${i.name} (x${i.quantity || 1})`).join(', ') || 'Sản phẩm đơn hàng';
                          return (
                            <tr key={ord.order_id} className="hover:bg-slate-50/80">
                              <td className="px-4 py-3.5 font-mono font-bold text-indigo-700 whitespace-nowrap">
                                {ord.order_id}
                              </td>
                              <td className="px-4 py-3.5 text-slate-800 max-w-xs">
                                <div className="flex items-start gap-1.5">
                                  <Package className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                                  <span className="font-medium leading-snug">{productNames}</span>
                                </div>
                              </td>
                              <td className="px-4 py-3.5 whitespace-nowrap">
                                <div className="font-bold text-slate-900">
                                  {Number(ord.total_amount || 0).toLocaleString('vi-VN')} ₫
                                </div>
                                <div className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5">
                                  <CreditCard className="w-3 h-3" />
                                  {ord.payment_method} ({ord.payment_status})
                                </div>
                              </td>
                              <td className="px-4 py-3.5 text-slate-600">
                                <div className="flex items-center gap-1 font-medium text-slate-700">
                                  <Truck className="w-3.5 h-3.5 text-slate-400" />
                                  {ord.carrier || 'TikiNOW'}
                                </div>
                                <div className="text-[10px] font-mono text-slate-400">
                                  {ord.tracking_code || ''} • {ord.estimated_delivery || ''}
                                </div>
                              </td>
                              <td className="px-4 py-3.5 whitespace-nowrap">
                                <span className="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                                  {ord.order_status}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Sub-tab 2: Chat Sessions History & Direct Staff Intervention */}
            {subTab === 'chats' && (
              <div className="flex-1 grid grid-cols-1 md:grid-cols-12 overflow-hidden">
                {/* Session list */}
                <div className="md:col-span-4 border-r border-slate-200 overflow-y-auto p-3 space-y-1.5 bg-slate-50/40">
                  <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Các phiên chat ({sessions.length})
                  </div>
                  {sessions.length === 0 ? (
                    <div className="p-4 text-xs text-slate-400 text-center">
                      Khách hàng chưa có phiên chat nào.
                    </div>
                  ) : (
                    sessions.map((s) => {
                      const active = s.sessionId === activeSessionId;
                      return (
                        <div
                          key={s.sessionId}
                          onClick={() => setActiveSessionId(s.sessionId)}
                          className={`p-3 rounded-xl cursor-pointer transition-all border ${
                            active
                              ? 'bg-white border-indigo-300 text-indigo-700 shadow-sm'
                              : 'hover:bg-white border-transparent text-slate-700'
                          }`}
                        >
                          <p className="text-xs font-bold truncate">{s.title || 'Hội thoại'}</p>
                          <div className="flex items-center justify-between mt-1 text-[10px] text-slate-400">
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {s.createdAt}
                            </span>
                            <span className="font-mono">{s.sessionId}</span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Transcript & Staff Intervention */}
                <div className="md:col-span-8 flex flex-col overflow-hidden bg-white">
                  <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3 bg-slate-50/30">
                    {!activeSessionId ? (
                      <div className="h-full flex items-center justify-center text-xs text-slate-400">
                        Chọn một phiên chat để xem nội dung trao đổi.
                      </div>
                    ) : sessionMessages.length === 0 ? (
                      <div className="h-full flex items-center justify-center text-xs text-slate-400">
                        Phiên chat này chưa có tin nhắn nào.
                      </div>
                    ) : (
                      sessionMessages.map((m, idx) => {
                        const isCust = m.role === 'customer';
                        let repliedQuestion: ChatMessage | null = null;
                        if (!isCust) {
                          for (let i = idx - 1; i >= 0; i--) {
                            if (sessionMessages[i].role === 'customer') {
                              repliedQuestion = sessionMessages[i];
                              break;
                            }
                          }
                        }
                        return (
                          <div key={m.id} className={`flex ${isCust ? 'justify-start' : 'justify-end'}`}>
                            <div className={`max-w-[80%] flex flex-col ${isCust ? 'items-start' : 'items-end'}`}>
                              {!isCust && repliedQuestion && (
                                <div className="mb-1 px-2.5 py-1 rounded-xl bg-slate-200/65 border border-slate-300/60 text-[10px] text-slate-600 max-w-full opacity-85 flex items-start gap-1">
                                  <CornerUpLeft className="w-3 h-3 text-slate-500 shrink-0 mt-0.5" />
                                  <span className="truncate italic">
                                    Trả lời {activeCustomer.name}: "{repliedQuestion.content}"
                                  </span>
                                </div>
                              )}
                              <div
                                className={`w-full px-3.5 py-2.5 rounded-2xl text-xs leading-relaxed shadow-sm whitespace-pre-wrap ${
                                  isCust
                                    ? 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm'
                                    : 'bg-blue-600 text-white rounded-tr-sm'
                                }`}
                              >
                                <div className="text-[10px] font-bold opacity-80 mb-0.5">
                                  {isCust ? `👤 Khách hàng (${activeCustomer.name})` : '👨‍💼 Nhân viên CSKH / Bot'}
                                </div>
                                {m.content}
                                <div className="text-[9px] opacity-70 mt-1 text-right">{m.timestamp}</div>
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>

                  {/* Direct Staff Message Intervention Bar */}
                  {activeSessionId && (
                    <form
                      onSubmit={handleSendStaffIntervention}
                      className="p-3 border-t border-slate-200 bg-white flex items-center gap-2"
                    >
                      <input
                        type="text"
                        value={staffReplyText}
                        onChange={(e) => setStaffReplyText(e.target.value)}
                        placeholder={`Gửi tin nhắn trực tiếp với tư cách ${selectedStaffName}...`}
                        className="flex-1 px-3.5 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-indigo-500"
                      />
                      <button
                        type="submit"
                        disabled={!staffReplyText.trim() || isSendingReply}
                        className="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm"
                      >
                        <Send className="w-3.5 h-3.5" />
                        <span>Gửi can thiệp</span>
                      </button>
                    </form>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
};
