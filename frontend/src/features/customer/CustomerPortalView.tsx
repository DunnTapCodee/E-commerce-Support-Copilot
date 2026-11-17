import React, { useEffect, useRef, useState } from 'react';
import {
  Bot,
  User,
  Plus,
  MessageSquare,
  Settings,
  Send,
  ArrowLeftRight,
  Trash2,
  BookOpen,
  X,
  Check,
  Sparkles,
  FileText,
  Copy,
  CornerUpLeft,
} from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { ChatMessage, CustomerProfileRecord, RetrievedDocument } from '../../types';
import { formatSystemTime } from '../../lib/time';

interface CustomerPortalViewProps {
  onSwitchRole: () => void;
}

interface CustomerSessionItem {
  sessionId: string;
  customerId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
}

interface ChatSettings {
  showCitations: boolean;
  autoScroll: boolean;
  fontSize: 'sm' | 'base';
}

const FALLBACK_CUSTOMERS: CustomerProfileRecord[] = [
  { customer_id: 'CUST-1100', name: 'Lê Văn Sơn', phone: '0998.708.581', email: 'son.le@customer.tiki.vn' },
  { customer_id: 'CUST-1002', name: 'Phan Văn An', phone: '0974.716.127', email: 'an.phan@customer.tiki.vn' },
  { customer_id: 'CUST-1001', name: 'Bùi Thị An', phone: '0938.242.854', email: 'an.bui@customer.tiki.vn' },
];

export const CustomerPortalView: React.FC<CustomerPortalViewProps> = ({ onSwitchRole }) => {
  const [customers, setCustomers] = useState<CustomerProfileRecord[]>(FALLBACK_CUSTOMERS);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>(() => {
    return localStorage.getItem('copilot_selected_cust') || 'CUST-1100';
  });

  const [sessions, setSessions] = useState<CustomerSessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({});
  const [pendingDraftBySession, setPendingDraftBySession] = useState<Record<string, string>>({});
  const [replyMode, setReplyMode] = useState<'staff_copilot' | 'auto_bot'>('staff_copilot');

  const [inputQuery, setInputQuery] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);

  // Settings Modal state
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [customerOverrides, setCustomerOverrides] = useState<Record<string, { name: string; phone: string; email: string }>>(() => {
    try {
      return JSON.parse(localStorage.getItem('customer_profile_overrides') || '{}');
    } catch {
      return {};
    }
  });
  const [chatSettings, setChatSettings] = useState<ChatSettings>(() => {
    try {
      return JSON.parse(localStorage.getItem('customer_chat_settings') || '{"showCitations":true,"autoScroll":true,"fontSize":"sm"}');
    } catch {
      return { showCitations: true, autoScroll: true, fontSize: 'sm' };
    }
  });

  // Draft form state inside Settings Modal
  const [editName, setEditName] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [settingsSavedBanner, setSettingsSavedBanner] = useState(false);

  // Policy catalog & Policy Viewer Modal state
  const [allPolicies, setAllPolicies] = useState<RetrievedDocument[]>([]);
  const [viewingPolicy, setViewingPolicy] = useState<RetrievedDocument | null>(null);
  const [copiedPolicy, setCopiedPolicy] = useState(false);

  const messagesContainerRef = useRef<HTMLDivElement | null>(null);

  // 1. Load customer list & policy list from Database via Gateway
  useEffect(() => {
    let mounted = true;
    const loadInitialData = async () => {
      try {
        const [list, policies] = await Promise.all([
          apiClient.listCustomers(),
          apiClient.listPolicies().catch(() => []),
        ]);
        if (!mounted) return;
        if (list.length > 0) {
          setCustomers(list);
          setSelectedCustomerId((prev) => (list.some((c) => c.customer_id === prev) ? prev : list[0].customer_id));
        }
        if (Array.isArray(policies) && policies.length > 0) {
          setAllPolicies(policies);
        }
      } catch (e) {
        console.warn('Load customer portal initial data error:', e);
      }
    };
    loadInitialData();
    return () => {
      mounted = false;
    };
  }, []);

  const currentCustomerBase = customers.find((c) => c.customer_id === selectedCustomerId) || customers[0];
  const currentOverride = customerOverrides[selectedCustomerId];
  const activeCustomer = {
    ...currentCustomerBase,
    name: currentOverride?.name || currentCustomerBase?.name || selectedCustomerId,
    phone: currentOverride?.phone ?? currentCustomerBase?.phone ?? '',
    email: currentOverride?.email ?? currentCustomerBase?.email ?? '',
  };

  // 2. Load sessions whenever selectedCustomerId changes
  useEffect(() => {
    if (!selectedCustomerId) return;
    localStorage.setItem('copilot_selected_cust', selectedCustomerId);
    let mounted = true;

    const loadCustomerSessions = async () => {
      setIsLoadingSessions(true);
      const dbSessions = await apiClient.listSessions(selectedCustomerId);
      if (!mounted) return;

      if (dbSessions && dbSessions.length > 0) {
        setSessions(dbSessions);
        setActiveSessionId((prev) =>
          dbSessions.some((s) => s.sessionId === prev) ? prev : dbSessions[0].sessionId
        );
      } else {
        const newId = `sess_${Math.random().toString(36).substring(2, 9)}`;
        const newSession: CustomerSessionItem = {
          sessionId: newId,
          customerId: selectedCustomerId,
          title: 'Hội thoại mới',
          createdAt: formatSystemTime(),
          updatedAt: new Date().toISOString(),
          messageCount: 0,
        };
        setSessions([newSession]);
        setActiveSessionId(newId);
        await apiClient.createSession(newId, selectedCustomerId, 'Hội thoại mới');
      }
      setIsLoadingSessions(false);
    };

    loadCustomerSessions();
    return () => {
      mounted = false;
    };
  }, [selectedCustomerId]);

  // 3. Load session message history when activeSessionId changes + Poll every 2.5s for Staff replies
  useEffect(() => {
    if (!activeSessionId || !selectedCustomerId) return;
    let mounted = true;

    const syncFromBackend = async () => {
      if (isSending) return;
      try {
        const [dbSessions, details] = await Promise.all([
          apiClient.listSessions(selectedCustomerId),
          apiClient.getSessionDetails(activeSessionId),
        ]);
        if (!mounted) return;

        if (dbSessions && dbSessions.length > 0) {
          setSessions(dbSessions);
        }
        if (details && Array.isArray(details.messages)) {
          setMessagesBySession((prev) => ({
            ...prev,
            [activeSessionId]: details.messages,
          }));
          setPendingDraftBySession((prev) => ({
            ...prev,
            [activeSessionId]: details.copilotDraft || '',
          }));
        }
      } catch (err) {
        console.warn('Sync customer session error:', err);
      }
    };

    syncFromBackend();
    const timer = setInterval(syncFromBackend, 2500);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, [activeSessionId, selectedCustomerId, isSending]);

  const currentMessages = messagesBySession[activeSessionId] || [];

  // Auto scroll ONLY inside the chat messages container (never scrolls outer window)
  useEffect(() => {
    if (chatSettings.autoScroll && messagesContainerRef.current) {
      messagesContainerRef.current.scrollTo({
        top: messagesContainerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [currentMessages.length, chatSettings.autoScroll]);

  // Helper: Open policy viewer modal when user clicks a [POL-XXX] badge or attachment
  const handleOpenPolicyDoc = (docId: string, citations?: RetrievedDocument[]) => {
    const cleanId = docId.replace(/[\[\]\(\)]/g, '').trim().toUpperCase();
    const found =
      citations?.find((c) => c.doc_id.toUpperCase() === cleanId) ||
      allPolicies.find((p) => p.doc_id.toUpperCase() === cleanId);

    if (found) {
      setViewingPolicy(found);
    } else {
      setViewingPolicy({
        doc_id: cleanId,
        title: `Văn bản quy định [${cleanId}]`,
        content: `Tài liệu chính sách ${cleanId} áp dụng trên hệ thống thương mại điện tử Tiki.`,
        version: '2.0',
        is_active: true,
        policy_type: 'permanent',
        tags: [cleanId],
      });
    }
  };

  const handleCopyPolicy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedPolicy(true);
    setTimeout(() => setCopiedPolicy(false), 2000);
  };

  // Helper: Find the customer question that a given agent message is replying to (Messenger-style quote)
  const findRepliedCustomerQuestion = (msgs: ChatMessage[], currentIdx: number): string | null => {
    const collected: string[] = [];
    for (let i = currentIdx - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === 'customer') {
        collected.unshift(m.content);
      } else if (collected.length > 0) {
        break;
      }
    }
    return collected.length > 0 ? collected.join(' • ') : null;
  };

  // Helper: Render bold (**text**) and clickable [POL-XXX] badges inside message content
  const parseMarkdownBold = (rawText: string, keyPrefix: string) => {
    const boldRegex = /\*\*([^*]+)\*\*/g;
    const nodes: (string | React.ReactNode)[] = [];
    let lastIdx = 0;
    let bMatch: RegExpExecArray | null;

    while ((bMatch = boldRegex.exec(rawText)) !== null) {
      if (bMatch.index > lastIdx) {
        nodes.push(rawText.slice(lastIdx, bMatch.index));
      }
      nodes.push(
        <strong key={`${keyPrefix}-b-${bMatch.index}`} className="font-bold">
          {bMatch[1]}
        </strong>
      );
      lastIdx = bMatch.index + bMatch[0].length;
    }
    if (lastIdx < rawText.length) {
      nodes.push(rawText.slice(lastIdx));
    }
    return nodes;
  };

  const renderTextWithPolicyLinks = (text: string, citations?: RetrievedDocument[]) => {
    if (!text) return null;
    const regex = /((?:\[|\()?(POL-[A-Z0-9_-]+)(?:\]|\))?)/g;
    const parts: (string | React.ReactNode)[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(text)) !== null) {
      const fullMatch = match[1];
      const docCode = match[2];
      const matchStart = match.index;

      if (matchStart > lastIndex) {
        const textChunk = text.slice(lastIndex, matchStart);
        parts.push(...parseMarkdownBold(textChunk, `pre-${matchStart}`));
      }

      parts.push(
        <button
          key={`policy-${matchStart}-${docCode}`}
          type="button"
          onClick={() => handleOpenPolicyDoc(docCode, citations)}
          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 mx-0.5 rounded-md font-mono text-[11px] font-bold text-blue-700 bg-blue-100 hover:bg-blue-200 border border-blue-300/80 cursor-pointer transition-colors shadow-2xs align-baseline"
          title={`Bấm để mở xem nội dung chính sách ${docCode}`}
        >
          <FileText className="w-2.5 h-2.5 text-blue-600 inline mr-0.5" />
          <span>{docCode}</span>
        </button>
      );

      lastIndex = matchStart + fullMatch.length;
    }

    if (lastIndex < text.length) {
      const textChunk = text.slice(lastIndex);
      parts.push(...parseMarkdownBold(textChunk, `post-${lastIndex}`));
    }

    return parts;
  };

  const handleCreateSession = async () => {
    const newId = `sess_${Math.random().toString(36).substring(2, 9)}`;
    const newSession: CustomerSessionItem = {
      sessionId: newId,
      customerId: selectedCustomerId,
      title: 'Hội thoại mới',
      createdAt: formatSystemTime(),
      updatedAt: new Date().toISOString(),
      messageCount: 0,
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newId);
    setMessagesBySession((prev) => ({ ...prev, [newId]: [] }));
    await apiClient.createSession(newId, selectedCustomerId, 'Hội thoại mới');
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    await apiClient.deleteSession(sessionId);
    const remaining = sessions.filter((s) => s.sessionId !== sessionId);
    if (remaining.length > 0) {
      setSessions(remaining);
      if (activeSessionId === sessionId) {
        setActiveSessionId(remaining[0].sessionId);
      }
    } else {
      await handleCreateSession();
    }
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const query = inputQuery.trim();
    if (!query || isSending || !activeSessionId) return;

    setInputQuery('');
    setIsSending(true);
    const currentSessId = activeSessionId;

    const userMsg: ChatMessage = {
      id: `msg_${Date.now()}_u`,
      role: 'customer',
      content: query,
      timestamp: formatSystemTime(),
    };

    // Optimistic append
    setMessagesBySession((prev) => ({
      ...prev,
      [currentSessId]: [...(prev[currentSessId] || []), userMsg],
    }));

    // Auto update session title if first message
    const activeSess = sessions.find((s) => s.sessionId === currentSessId);
    if (activeSess && (activeSess.title === 'Hội thoại mới' || activeSess.title === 'Hội thoại')) {
      const shortTitle = query.length > 32 ? `${query.slice(0, 32)}...` : query;
      setSessions((prev) => prev.map((s) => (s.sessionId === currentSessId ? { ...s, title: shortTitle } : s)));
      apiClient.updateSessionTitle(currentSessId, shortTitle);
    }

    try {
      // 1. Always persist Customer message into SQLite first so Staff sees it immediately
      await apiClient.saveMessage(currentSessId, 'customer', query, false, selectedCustomerId);

      // 2. Trigger Copilot orchestration (which also saves copilot_draft & copilot_response_json to SQLite)
      const resp = await apiClient.sendQuery(query, currentSessId, selectedCustomerId);
      const ackText =
        resp.customer_acknowledgement?.trim() ||
        'Dạ Tiki đã ghi nhận thông tin của anh/chị. Nhân viên CSKH đang kiểm tra hồ sơ và sẽ phản hồi ngay trong giây lát ạ!';
      const draftText =
        resp.draft_text?.trim() ||
        resp.suggested_reply?.trim() ||
        ackText;

      if (replyMode === 'staff_copilot') {
        // Human-in-the-loop Copilot mode: Show immediate buffer ack to customer, keep draft in SQLite for Staff to approve on /staff!
        const ackMsg: ChatMessage = {
          id: `msg_${Date.now()}_ack`,
          role: 'agent',
          content: ackText,
          timestamp: formatSystemTime(),
          isAcknowledgement: true,
        };
        setMessagesBySession((prev) => ({
          ...prev,
          [currentSessId]: [...(prev[currentSessId] || []), ackMsg],
        }));
        setPendingDraftBySession((prev) => ({
          ...prev,
          [currentSessId]: draftText,
        }));
        await apiClient.saveMessage(currentSessId, 'acknowledgement', ackText, true, selectedCustomerId);
      } else {
        // Auto-bot mode: Immediately send draft as final agent reply
        const botMsg: ChatMessage = {
          id: `msg_${Date.now()}_b`,
          role: 'agent',
          content: draftText,
          timestamp: formatSystemTime(),
          citations: resp.citations || [],
          isAcknowledgement: false,
        };
        setMessagesBySession((prev) => ({
          ...prev,
          [currentSessId]: [...(prev[currentSessId] || []), botMsg],
        }));
        setPendingDraftBySession((prev) => ({
          ...prev,
          [currentSessId]: '',
        }));
        await apiClient.saveMessage(currentSessId, 'agent', draftText, false, selectedCustomerId);
      }
    } catch (err: any) {
      const errMsg: ChatMessage = {
        id: `msg_${Date.now()}_err`,
        role: 'system',
        content: `Không thể kết nối máy chủ hỗ trợ: ${err?.message || 'Lỗi mạng'}`,
        timestamp: formatSystemTime(),
      };
      setMessagesBySession((prev) => ({
        ...prev,
        [currentSessId]: [...(prev[currentSessId] || []), errMsg],
      }));
    } finally {
      setIsSending(false);
    }
  };

  // Allow customer testing alone to instantly approve the pending Copilot draft without leaving /customer
  const handleInstantAutoApprove = async () => {
    const draft = pendingDraftBySession[activeSessionId];
    if (!draft || !activeSessionId) return;
    const botMsg: ChatMessage = {
      id: `msg_${Date.now()}_auto`,
      role: 'agent',
      content: draft,
      timestamp: formatSystemTime(),
      isAcknowledgement: false,
    };
    setMessagesBySession((prev) => ({
      ...prev,
      [activeSessionId]: [...(prev[activeSessionId] || []), botMsg],
    }));
    setPendingDraftBySession((prev) => ({
      ...prev,
      [activeSessionId]: '',
    }));
    await apiClient.saveMessage(activeSessionId, 'agent', draft, false, selectedCustomerId);
  };

  const openSettings = () => {
    setEditName(activeCustomer.name || '');
    setEditPhone(activeCustomer.phone || '');
    setEditEmail(activeCustomer.email || '');
    setSettingsSavedBanner(false);
    setIsSettingsOpen(true);
  };

  const saveSettings = (e: React.FormEvent) => {
    e.preventDefault();
    const updatedOverrides = {
      ...customerOverrides,
      [selectedCustomerId]: {
        name: editName.trim() || activeCustomer.name,
        phone: editPhone.trim(),
        email: editEmail.trim(),
      },
    };
    setCustomerOverrides(updatedOverrides);
    localStorage.setItem('customer_profile_overrides', JSON.stringify(updatedOverrides));
    localStorage.setItem('customer_chat_settings', JSON.stringify(chatSettings));
    setSettingsSavedBanner(true);
    setTimeout(() => setIsSettingsOpen(false), 600);
  };

  const quickPrompts = [
    'Kiểm tra trạng thái đơn hàng gần nhất của tôi',
    'Chính sách đổi trả hàng hiện tại như thế nào?',
    'Hiện tại có mã giảm giá hay freeship nào không?',
  ];

  return (
    <div className="h-screen overflow-hidden flex flex-col bg-slate-50">
      {/* Top Header (Fixed, never scrolls) */}
      <header className="bg-white border-b border-slate-200 shrink-0 z-30 shadow-sm">
        <div className="w-full max-w-[1600px] mx-auto px-4 h-16 flex items-center justify-between gap-4">
          {/* Left Brand */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-slate-900">Trợ lý Hỗ trợ Khách hàng</h1>
                <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  Khách hàng
                </span>
              </div>
              <p className="text-[11px] text-slate-500">Hỏi đáp đơn hàng, vận chuyển & chính sách sàn Tiki 24/7</p>
            </div>
          </div>

          {/* Right Controls: Customer Selector + Switch Role */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5">
              <User className="w-4 h-4 text-blue-600 shrink-0" />
              <label htmlFor="customer-selector" className="text-xs font-medium text-slate-600 hidden sm:inline">
                Tài khoản:
              </label>
              <select
                id="customer-selector"
                value={selectedCustomerId}
                onChange={(e) => setSelectedCustomerId(e.target.value)}
                className="bg-transparent text-xs sm:text-sm font-semibold text-slate-800 focus:outline-none cursor-pointer"
              >
                {customers.map((c) => {
                  const ov = customerOverrides[c.customer_id];
                  const displayName = ov?.name || c.name;
                  return (
                    <option key={c.customer_id} value={c.customer_id}>
                      {displayName} ({c.customer_id})
                    </option>
                  );
                })}
              </select>
            </div>

            <button
              type="button"
              onClick={onSwitchRole}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 hover:text-slate-900 transition-colors shadow-sm"
            >
              <ArrowLeftRight className="w-3.5 h-3.5 text-blue-600" />
              <span>Đổi vai trò</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area (Locked to remaining viewport height, never scrolls outer page) */}
      <div className="flex-1 min-h-0 w-full max-w-[1600px] mx-auto p-3 sm:p-4 grid grid-cols-1 lg:grid-cols-12 gap-4 overflow-hidden">
        {/* Left Sidebar */}
        <aside className="lg:col-span-3 h-full min-h-0 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          {/* Customer Quick Card */}
          <div className="p-4 border-b border-slate-100 bg-gradient-to-r from-blue-50/70 to-indigo-50/40 shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-slate-800">{activeCustomer.name}</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white text-slate-600 border border-slate-200">
                {activeCustomer.customer_id}
              </span>
            </div>
            <p className="text-[11px] text-slate-500">
              {activeCustomer.phone || 'Chưa cập nhật SĐT'} {activeCustomer.email ? `• ${activeCustomer.email}` : ''}
            </p>
          </div>

          {/* New Session Button */}
          <div className="p-3 border-b border-slate-100 shrink-0">
            <button
              type="button"
              onClick={handleCreateSession}
              className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>Tạo phiên chat mới</span>
            </button>
          </div>

          {/* Sessions List (Scrolls independently) */}
          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-2 space-y-1">
            <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Lịch sử phiên chat ({sessions.length})
            </div>

            {isLoadingSessions ? (
              <div className="p-4 text-center text-xs text-slate-400">Đang tải lịch sử...</div>
            ) : (
              sessions.map((sess) => {
                const isActive = sess.sessionId === activeSessionId;
                return (
                  <div
                    key={sess.sessionId}
                    onClick={() => setActiveSessionId(sess.sessionId)}
                    className={`group flex items-center justify-between px-3 py-2.5 rounded-xl cursor-pointer transition-all ${
                      isActive
                        ? 'bg-blue-50 text-blue-700 border border-blue-200'
                        : 'hover:bg-slate-50 text-slate-700 border border-transparent'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <MessageSquare className={`w-4 h-4 shrink-0 ${isActive ? 'text-blue-600' : 'text-slate-400'}`} />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold truncate">{sess.title || 'Hội thoại mới'}</p>
                        <p className="text-[10px] text-slate-400 truncate">{sess.createdAt}</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => handleDeleteSession(e, sess.sessionId)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition-all"
                      title="Xóa phiên chat"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>

          {/* Bottom Settings Button */}
          <div className="p-3 border-t border-slate-100 bg-slate-50/70 shrink-0">
            <button
              type="button"
              onClick={openSettings}
              className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
            >
              <Settings className="w-4 h-4 text-slate-500" />
              <span>Cài đặt (Settings)</span>
            </button>
          </div>
        </aside>

        {/* Main Chat Frame */}
        <section className="lg:col-span-9 h-full min-h-0 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          {/* Chat Header */}
          <div className="px-5 py-3 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2 bg-white shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <div>
                <h2 className="text-sm font-bold text-slate-800">
                  {sessions.find((s) => s.sessionId === activeSessionId)?.title || 'Hội thoại hỗ trợ'}
                </h2>
                <p className="text-[11px] text-slate-400">
                  Khách hàng: <span className="font-semibold text-slate-600">{activeCustomer.name} ({selectedCustomerId})</span>
                  {' • '}Phiên: <span className="font-mono">{activeSessionId}</span>
                </p>
              </div>
            </div>

            {/* Reply Mode Switcher */}
            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl text-[11px]">
              <button
                type="button"
                onClick={() => setReplyMode('staff_copilot')}
                className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer ${
                  replyMode === 'staff_copilot'
                    ? 'bg-white text-blue-700 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
                title="Gửi câu hỏi sang màn hình Nhân viên (/staff) để Copilot soạn nháp và Nhân viên bấm Duyệt"
              >
                👨‍💼 Nhân viên + Copilot duyệt
              </button>
              <button
                type="button"
                onClick={() => setReplyMode('auto_bot')}
                className={`px-2.5 py-1 rounded-lg font-semibold transition-all cursor-pointer ${
                  replyMode === 'auto_bot'
                    ? 'bg-white text-emerald-700 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
                title="Bot AI tự động trả lời ngay lập tức không cần chờ Nhân viên duyệt"
              >
                🤖 Bot trả lời tự động
              </button>
            </div>
          </div>

          {/* Messages Area (ONLY this container scrolls when wheeling inside chat) */}
          <div
            ref={messagesContainerRef}
            className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4 sm:p-6 space-y-4 bg-slate-50/50"
          >
            {currentMessages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center max-w-md mx-auto py-10">
                <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-3">
                  <Sparkles className="w-6 h-6" />
                </div>
                <h3 className="text-base font-bold text-slate-800 mb-1">
                  Xin chào {activeCustomer.name}!
                </h3>
                <p className="text-xs text-slate-500 mb-5">
                  Em là trợ lý hỗ trợ của Tiki. Anh/chị cần kiểm tra đơn hàng, đổi trả hay hỏi về ưu đãi hôm nay ạ?
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {quickPrompts.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => setInputQuery(q)}
                      className="text-xs px-3 py-1.5 rounded-full bg-white border border-slate-200 hover:border-blue-400 hover:text-blue-600 text-slate-600 transition-colors shadow-sm cursor-pointer"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              currentMessages.map((msg, idx) => {
                const isCustomer = msg.role === 'customer';
                const isSystem = msg.role === 'system';
                const isAck = Boolean(msg.isAcknowledgement || msg.role === 'acknowledgement');
                const textSize = chatSettings.fontSize === 'base' ? 'text-sm' : 'text-xs sm:text-[13px]';

                if (isSystem) {
                  return (
                    <div key={msg.id} className="flex justify-center">
                      <span className="px-3 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 text-xs">
                        {msg.content}
                      </span>
                    </div>
                  );
                }

                // Messenger-style quoted customer question for agent/ack replies
                const repliedQuestion = !isCustomer ? findRepliedCustomerQuestion(currentMessages, idx) : null;

                // Collect policy codes mentioned inside msg.content or msg.citations
                const citedMatches = !isCustomer ? msg.content.match(/POL-[A-Z0-9_-]+/gi) || [] : [];
                const uniquePolicyCodes = Array.from(
                  new Set([
                    ...citedMatches.map((c) => c.toUpperCase()),
                    ...(msg.citations || []).map((c) => c.doc_id.toUpperCase()),
                  ])
                );

                return (
                  <div key={msg.id} className={`flex ${isCustomer ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[82%] sm:max-w-[72%] flex flex-col ${isCustomer ? 'items-end' : 'items-start'}`}>
                      {/* Messenger-style Faded Quoted Question above reply */}
                      {!isCustomer && repliedQuestion && (
                        <div className="mb-1 ml-1 px-3 py-1.5 rounded-xl bg-slate-200/60 border-l-2 border-slate-400 text-[11px] text-slate-500 max-w-full">
                          <div className="flex items-center gap-1 font-semibold text-slate-600 text-[10px]">
                            <CornerUpLeft className="w-3 h-3 text-slate-500 shrink-0" />
                            <span>Trả lời câu hỏi của bạn:</span>
                          </div>
                          <p className="italic truncate opacity-85">"{repliedQuestion}"</p>
                        </div>
                      )}

                      <div
                        className={`px-4 py-2.5 rounded-2xl leading-relaxed shadow-sm whitespace-pre-wrap ${textSize} ${
                          isCustomer
                            ? 'bg-blue-600 text-white rounded-br-sm'
                            : isAck
                              ? 'bg-amber-50/90 text-amber-950 border border-amber-200 rounded-bl-sm'
                              : 'bg-white text-slate-800 border border-slate-200 rounded-bl-sm'
                        }`}
                      >
                        {!isCustomer && (
                          <div
                            className={`text-[10px] font-bold mb-1.5 pb-1 border-b ${
                              isAck ? 'text-amber-700 border-amber-200/60' : 'text-emerald-700 border-slate-100'
                            }`}
                          >
                            {isAck ? '⚡ Hệ thống tiếp nhận (Đang chuyển Nhân viên CSKH)' : '👤 Phản hồi chính thức từ CSKH Tiki'}
                          </div>
                        )}
                        <div className="leading-relaxed whitespace-pre-wrap">
                          {isCustomer ? msg.content : renderTextWithPolicyLinks(msg.content, msg.citations)}
                        </div>
                      </div>

                      {/* Clickable Policy Citations below message bubble */}
                      {!isCustomer && chatSettings.showCitations && uniquePolicyCodes.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {uniquePolicyCodes.map((code) => {
                            const matchedDoc =
                              msg.citations?.find((c) => c.doc_id.toUpperCase() === code) ||
                              allPolicies.find((p) => p.doc_id.toUpperCase() === code);
                            return (
                              <button
                                key={code}
                                type="button"
                                onClick={() => handleOpenPolicyDoc(code, msg.citations)}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 transition-colors cursor-pointer shadow-2xs"
                                title="Bấm để mở xem nội dung văn bản chính sách"
                              >
                                <BookOpen className="w-3 h-3 text-indigo-600" />
                                <span>
                                  [{code}] {matchedDoc?.title ? `• ${matchedDoc.title}` : 'Xem chính sách'}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      )}

                      <span className="mt-1 text-[10px] text-slate-400 px-1">{msg.timestamp}</span>
                    </div>
                  </div>
                );
              })
            )}

            {isSending && (
              <div className="flex justify-start">
                <div className="px-4 py-2.5 rounded-2xl bg-white border border-slate-200 text-xs text-slate-500 shadow-sm">
                  Đang gửi tin nhắn & đồng bộ với bộ phận CSKH...
                </div>
              </div>
            )}
          </div>

          {/* Pending Staff Copilot Approval Banner */}
          {pendingDraftBySession[activeSessionId] && !isSending && (
            <div className="px-4 py-2 bg-amber-50/90 border-t border-amber-200 flex flex-wrap items-center justify-between gap-2 text-xs shrink-0">
              <span className="text-amber-800 font-medium">
                ⏳ <b>Copilot đã soạn xong bản nháp!</b> Nhân viên có thể duyệt gửi bên màn hình <b>/staff</b>, hoặc bạn có thể nhận câu trả lời ngay:
              </span>
              <button
                type="button"
                onClick={handleInstantAutoApprove}
                className="px-3 py-1 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold text-[11px] transition-colors cursor-pointer shadow-2xs"
              >
                ⚡ Nhận phản hồi AI ngay
              </button>
            </div>
          )}

          {/* Input Bar */}
          <form onSubmit={handleSendMessage} className="p-3 sm:p-4 border-t border-slate-200 bg-white flex items-center gap-2.5 shrink-0">
            <input
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              placeholder="Nhập câu hỏi về đơn hàng, vận chuyển, chính sách đổi trả..."
              disabled={isSending}
              className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:border-blue-500 focus:outline-none text-sm text-slate-800"
            />
            <button
              type="submit"
              disabled={isSending || !inputQuery.trim()}
              className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white font-semibold text-sm flex items-center gap-2 transition-colors shadow-sm cursor-pointer"
            >
              <Send className="w-4 h-4" />
              <span className="hidden sm:inline">Gửi</span>
            </button>
          </form>
        </section>
      </div>

      {/* Policy Document Viewer Modal (with "X" button to close) */}
      {viewingPolicy && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/45 backdrop-blur-xs flex items-center justify-center p-4"
          onClick={() => setViewingPolicy(null)}
        >
          <div
            className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-xl overflow-hidden animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header with X close button */}
            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center shrink-0">
                  <FileText className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-slate-900 truncate">
                    [{viewingPolicy.doc_id}] {viewingPolicy.title}
                  </h3>
                  <p className="text-[11px] text-slate-500">Văn bản chính sách hỗ trợ khách hàng Tiki</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setViewingPolicy(null)}
                className="w-8 h-8 rounded-xl flex items-center justify-center bg-white border border-slate-200 text-slate-500 hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors cursor-pointer shrink-0"
                title="Đóng (X)"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Policy Metadata Bar */}
            <div className="px-5 py-2.5 bg-white border-b border-slate-100 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Trạng thái:</span>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    viewingPolicy.is_active
                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                      : 'bg-red-50 text-red-700 border border-red-200'
                  }`}
                >
                  {viewingPolicy.is_active ? 'Đang áp dụng (Active)' : 'Ngừng áp dụng'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => handleCopyPolicy(viewingPolicy.content)}
                className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700 cursor-pointer"
              >
                {copiedPolicy ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedPolicy ? 'Đã sao chép!' : 'Sao chép nội dung'}</span>
              </button>
            </div>

            {/* Policy Content Body */}
            <div className="p-5">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 max-h-72 overflow-y-auto overscroll-contain whitespace-pre-wrap text-xs sm:text-[13px] text-slate-700 leading-relaxed">
                {viewingPolicy.content}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/50 flex justify-end">
              <button
                type="button"
                onClick={() => setViewingPolicy(null)}
                className="px-4 py-2 rounded-xl bg-slate-200/80 hover:bg-slate-300/80 text-slate-700 text-xs font-semibold transition-colors cursor-pointer"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {isSettingsOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl w-full max-w-md overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Settings className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-900">Cài đặt Khách hàng & Hiển thị</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsSettingsOpen(false)}
                className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={saveSettings} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Tên hiển thị</label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Số điện thoại</label>
                  <input
                    type="text"
                    value={editPhone}
                    onChange={(e) => setEditPhone(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Email</label>
                  <input
                    type="email"
                    value={editEmail}
                    onChange={(e) => setEditEmail(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="pt-2 border-t border-slate-100 space-y-2.5">
                <p className="text-xs font-bold text-slate-700">Tùy chọn hiển thị khung chat</p>
                <label className="flex items-center justify-between text-xs text-slate-600 cursor-pointer">
                  <span>Hiển thị mã chính sách trích dẫn ([POL-...])</span>
                  <input
                    type="checkbox"
                    checked={chatSettings.showCitations}
                    onChange={(e) => setChatSettings((s) => ({ ...s, showCitations: e.target.checked }))}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                </label>
                <label className="flex items-center justify-between text-xs text-slate-600 cursor-pointer">
                  <span>Tự động cuộn xuống tin nhắn mới nhất</span>
                  <input
                    type="checkbox"
                    checked={chatSettings.autoScroll}
                    onChange={(e) => setChatSettings((s) => ({ ...s, autoScroll: e.target.checked }))}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                </label>
                <div className="flex items-center justify-between text-xs text-slate-600">
                  <span>Cỡ chữ tin nhắn</span>
                  <select
                    value={chatSettings.fontSize}
                    onChange={(e) => setChatSettings((s) => ({ ...s, fontSize: e.target.value as 'sm' | 'base' }))}
                    className="px-2 py-1 rounded-lg border border-slate-200 text-xs bg-white"
                  >
                    <option value="sm">Tiêu chuẩn</option>
                    <option value="base">Lớn hơn</option>
                  </select>
                </div>
              </div>

              {settingsSavedBanner && (
                <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-2 rounded-xl">
                  <Check className="w-4 h-4" />
                  <span>Đã lưu cài đặt thành công!</span>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsSettingsOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100"
                >
                  Đóng
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white shadow-sm"
                >
                  Lưu thay đổi
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
