import React, { useState, useEffect, useRef } from 'react';
import {
  Send,
  User,
  Bot,
  RefreshCw,
  CheckCircle,
  FileText,
  Clock,
  Plus,
  Trash2,
  Package,
  Phone,
  MessageSquare,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Edit2,
  Check,
  X,
  Copy,
  Zap,
  Info,
  Sliders,
  ExternalLink,
  Eye,
} from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { GatewayResponse, RetrievedDocument } from '../../types';
import { formatSystemTime } from '../../lib/time';

export interface ChatMessage {
  id: string;
  role: 'customer' | 'agent' | 'system';
  content: string;
  timestamp: string;
  citations?: RetrievedDocument[];
  isAcknowledgement?: boolean;
}

export interface CustomerProfile {
  id: string;
  name: string;
  phone: string;
  orderId?: string;
  orderStatus?: string;
}

export const MOCK_CUSTOMERS: CustomerProfile[] = [
  {
    id: 'CUST-1100',
    name: 'Lê Văn Sơn',
    phone: '0998.708.581',
    orderId: 'ORD-1100',
    orderStatus: 'Đã giao hàng (DELIVERED)',
  },
  {
    id: 'CUST-1002',
    name: 'Phan Văn An',
    phone: '0974.716.127',
    orderId: 'ORD-1002',
    orderStatus: 'Đang vận chuyển (SHIPPING)',
  },
  {
    id: 'CUST-1001',
    name: 'Bùi Thị An',
    phone: '0938.242.854',
    orderId: 'ORD-1001',
    orderStatus: 'Chờ giao hàng (PROCESSING)',
  },
  {
    id: 'CUST-1003',
    name: 'Vũ Thanh Linh',
    phone: '0999.532.448',
    orderId: 'ORD-1003',
    orderStatus: 'Đã hủy đơn (CANCELLED)',
  },
];

export interface ConversationSession {
  sessionId: string;
  customerId: string;
  title: string;
  createdAt: string;
  updatedAt?: string;
  messages: ChatMessage[];
  copilotResponse: GatewayResponse | null;
  editedDraft: string;
}

export const ChatView: React.FC = () => {
  // Selected customer state with localStorage backup
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>(() => {
    return localStorage.getItem('copilot_selected_cust') || 'CUST-1100';
  });

  // Customer sessions map: customerId -> ConversationSession[]
  const [sessionsByCustomer, setSessionsByCustomer] = useState<Record<string, ConversationSession[]>>(() => {
    const cached = localStorage.getItem('copilot_sessions_cache');
    if (cached) {
      try {
        return JSON.parse(cached);
      } catch (e) {}
    }
    const initialSessionId = `sess_${Math.random().toString(36).substring(2, 9)}`;
    return {
      'CUST-1100': [
        {
          sessionId: initialSessionId,
          customerId: 'CUST-1100',
          title: 'Tra cứu đơn ORD-1100',
          createdAt: formatSystemTime(),
          updatedAt: new Date().toISOString(),
          messages: [],
          copilotResponse: null,
          editedDraft: '',
        },
      ],
    };
  });

  // Active session ID
  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    const list = sessionsByCustomer[selectedCustomerId] || [];
    return list[0]?.sessionId || '';
  });

  const [inputQuery, setInputQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // E-commerce multi-message: Toggle auto-request vs manual "Yêu cầu trả lời"
  const [autoTriggerCopilot, setAutoTriggerCopilot] = useState<boolean>(true);

  // Rename session inline state
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [tempTitle, setTempTitle] = useState('');

  // Policy modal viewer state
  const [viewingPolicy, setViewingPolicy] = useState<RetrievedDocument | null>(null);
  const [copiedPolicy, setCopiedPolicy] = useState(false);

  // Collapsible state for Copilot Smart Analysis
  const [showAnalysisDetails, setShowAnalysisDetails] = useState(false);

  // Toggle between interactive POL preview vs direct textarea editing (fixes duplicate drafts)
  const [draftMode, setDraftMode] = useState<'preview' | 'edit'>('preview');

  // IDE-style Resizable Panel Widths (in pixels)
  const containerRef = useRef<HTMLDivElement>(null);
  const dragModeRef = useRef<'left' | 'right' | null>(null);

  const [leftWidth, setLeftWidth] = useState<number>(() => {
    const saved = localStorage.getItem('copilot_left_width');
    return saved ? parseInt(saved, 10) : 280;
  });
  const [rightWidth, setRightWidth] = useState<number>(() => {
    const saved = localStorage.getItem('copilot_right_width');
    return saved ? parseInt(saved, 10) : 420;
  });

  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

  const startDragLeft = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragModeRef.current = 'left';
    setIsDraggingLeft(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const startDragRight = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragModeRef.current = 'right';
    setIsDraggingRight(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  // High-performance resizable panels mouse listener: accurately measures relative to containerRect
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const mode = dragModeRef.current;
      if (!mode || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();

      if (mode === 'left') {
        const rawWidth = e.clientX - rect.left;
        const newWidth = Math.min(Math.max(rawWidth, 210), 450);
        setLeftWidth(newWidth);
        localStorage.setItem('copilot_left_width', String(newWidth));
      } else if (mode === 'right') {
        const rawWidth = rect.right - e.clientX;
        const newWidth = Math.min(Math.max(rawWidth, 310), 650);
        setRightWidth(newWidth);
        localStorage.setItem('copilot_right_width', String(newWidth));
      }
    };

    const handleMouseUp = () => {
      if (dragModeRef.current) {
        dragModeRef.current = null;
        setIsDraggingLeft(false);
        setIsDraggingRight(false);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // Sync cache to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('copilot_sessions_cache', JSON.stringify(sessionsByCustomer));
    } catch (e) {}
  }, [sessionsByCustomer]);

  useEffect(() => {
    localStorage.setItem('copilot_selected_cust', selectedCustomerId);
  }, [selectedCustomerId]);

  // Load persistent sessions from backend SQLite database on mount / customer switch
  useEffect(() => {
    let isMounted = true;
    const loadBackendSessions = async () => {
      try {
        const dbSessions = await apiClient.listSessions(selectedCustomerId);
        if (isMounted && dbSessions && dbSessions.length > 0) {
          setSessionsByCustomer((prev) => {
            const currentList = prev[selectedCustomerId] || [];
            const mergedMap = new Map<string, ConversationSession>();
            currentList.forEach((s) => mergedMap.set(s.sessionId, s));

            dbSessions.forEach((ds) => {
              if (!mergedMap.has(ds.sessionId)) {
                mergedMap.set(ds.sessionId, {
                  sessionId: ds.sessionId,
                  customerId: ds.customerId,
                  title: ds.title,
                  createdAt: ds.createdAt ? formatSystemTime(ds.createdAt) : formatSystemTime(),
                  updatedAt: ds.updatedAt || new Date().toISOString(),
                  messages: [],
                  copilotResponse: null,
                  editedDraft: '',
                });
              }
            });

            // Keep sorted newest first
            const merged = Array.from(mergedMap.values());
            return {
              ...prev,
              [selectedCustomerId]: merged,
            };
          });

          // If no active session, pick first
          setActiveSessionId((curr) => curr || dbSessions[0].sessionId);
        }
      } catch (err) {
        console.warn('Load backend sessions error:', err);
      }
    };
    loadBackendSessions();
    return () => {
      isMounted = false;
    };
  }, [selectedCustomerId]);

  // Load message history from backend SQLite when selecting a session
  useEffect(() => {
    if (!activeSessionId) return;
    let isMounted = true;

    const loadHistory = async () => {
      try {
        const details = await apiClient.getSessionDetails(activeSessionId);
        if (isMounted && details && details.messages && details.messages.length > 0) {
          setSessionsByCustomer((prev) => {
            const list = prev[selectedCustomerId] || [];
            return {
              ...prev,
              [selectedCustomerId]: list.map((s) => {
                if (s.sessionId === activeSessionId) {
                  return {
                    ...s,
                    title: details.title || s.title,
                    messages: details.messages,
                    editedDraft: details.copilotDraft || s.editedDraft,
                    copilotResponse: details.copilotResponse || s.copilotResponse,
                  };
                }
                return s;
              }),
            };
          });
        }
      } catch (err) {
        console.warn('Load session history error:', err);
      }
    };
    loadHistory();
    return () => {
      isMounted = false;
    };
  }, [activeSessionId, selectedCustomerId]);

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
      const newSessId = `sess_${Math.random().toString(36).substring(2, 9)}`;
      const newSession: ConversationSession = {
        sessionId: newSessId,
        customerId: customerId,
        title: 'Hội thoại mới',
        createdAt: formatSystemTime(),
        updatedAt: new Date().toISOString(),
        messages: [],
        copilotResponse: null,
        editedDraft: '',
      };
      setSessionsByCustomer((prev) => ({
        ...prev,
        [customerId]: [newSession],
      }));
      setActiveSessionId(newSessId);
      apiClient.createSession(newSessId, customerId, 'Hội thoại mới');
    }
  };

  // Create new conversation session for current customer
  const handleCreateNewSession = () => {
    const newSessId = `sess_${Math.random().toString(36).substring(2, 9)}`;
    const count = (sessionsByCustomer[selectedCustomerId] || []).length + 1;
    const title = `Hội thoại #${count}`;
    const newSession: ConversationSession = {
      sessionId: newSessId,
      customerId: selectedCustomerId,
      title,
      createdAt: formatSystemTime(),
      updatedAt: new Date().toISOString(),
      messages: [],
      copilotResponse: null,
      editedDraft: '',
    };

    setSessionsByCustomer((prev) => ({
      ...prev,
      [selectedCustomerId]: [newSession, ...(prev[selectedCustomerId] || [])],
    }));
    setActiveSessionId(newSessId);

    // Save to backend SQLite
    apiClient.createSession(newSessId, selectedCustomerId, title);
  };

  // Delete a session
  const handleDeleteSession = (sessionIdToDelete: string, e: React.MouseEvent) => {
    e.stopPropagation();
    apiClient.deleteSession(sessionIdToDelete);

    const remaining = (sessionsByCustomer[selectedCustomerId] || []).filter(
      (s) => s.sessionId !== sessionIdToDelete
    );

    if (remaining.length === 0) {
      const newSessId = `sess_${Math.random().toString(36).substring(2, 9)}`;
      const newSession: ConversationSession = {
        sessionId: newSessId,
        customerId: selectedCustomerId,
        title: 'Hội thoại mới',
        createdAt: formatSystemTime(),
        updatedAt: new Date().toISOString(),
        messages: [],
        copilotResponse: null,
        editedDraft: '',
      };
      setSessionsByCustomer((prev) => ({
        ...prev,
        [selectedCustomerId]: [newSession],
      }));
      setActiveSessionId(newSessId);
      apiClient.createSession(newSessId, selectedCustomerId, 'Hội thoại mới');
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

  // Start renaming a session
  const handleStartRename = (s: ConversationSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingSessionId(s.sessionId);
    setTempTitle(s.title);
  };

  // Confirm rename session
  const handleSaveRename = (sessionId: string, e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!tempTitle.trim()) {
      setEditingSessionId(null);
      return;
    }
    const finalTitle = tempTitle.trim();
    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) => (s.sessionId === sessionId ? { ...s, title: finalTitle } : s)),
      };
    });
    setEditingSessionId(null);
    apiClient.updateSessionTitle(sessionId, finalTitle);
  };

  // Helper: Trigger Copilot draft generation for a query or collected customer queries (with real-time SSE token streaming)
  const triggerCopilotInference = async (queryText: string, currentSessionId: string, ackMsgId: string) => {
    setIsLoading(true);
    let streamedDraft = '';

    try {
      await apiClient.queryCopilotStream(
        queryText,
        currentSessionId,
        currentCustomer.id,
        {
          onMeta: (meta) => {
            setSessionsByCustomer((prev) => {
              const list = prev[selectedCustomerId] || [];
              return {
                ...prev,
                [selectedCustomerId]: list.map((s) => {
                  if (s.sessionId === currentSessionId) {
                    return {
                      ...s,
                      copilotResponse: {
                        ...(s.copilotResponse || {}),
                        ...meta,
                        draft_text: streamedDraft || s.editedDraft,
                      },
                    };
                  }
                  return s;
                }),
              };
            });
          },
          onToken: (delta) => {
            streamedDraft += delta;
            setSessionsByCustomer((prev) => {
              const list = prev[selectedCustomerId] || [];
              return {
                ...prev,
                [selectedCustomerId]: list.map((s) => {
                  if (s.sessionId === currentSessionId) {
                    return {
                      ...s,
                      editedDraft: streamedDraft,
                    };
                  }
                  return s;
                }),
              };
            });
          },
          onDone: (data) => {
            const finalDraft = data.draft_text || streamedDraft;
            setSessionsByCustomer((prev) => {
              const list = prev[selectedCustomerId] || [];
              return {
                ...prev,
                [selectedCustomerId]: list.map((s) => {
                  if (s.sessionId === currentSessionId) {
                    return {
                      ...s,
                      editedDraft: finalDraft,
                      copilotResponse: s.copilotResponse
                        ? { ...s.copilotResponse, draft_text: finalDraft }
                        : null,
                    };
                  }
                  return s;
                }),
              };
            });
            setIsLoading(false);
          },
          onError: async (err) => {
            console.warn('Streaming failed, falling back to synchronous sendQuery:', err);
            const resp = await apiClient.sendQuery(queryText, currentSessionId, currentCustomer.id);
            setSessionsByCustomer((prev) => {
              const list = prev[selectedCustomerId] || [];
              return {
                ...prev,
                [selectedCustomerId]: list.map((s) => {
                  if (s.sessionId === currentSessionId) {
                    return {
                      ...s,
                      copilotResponse: resp,
                      editedDraft: resp.draft_text || '',
                    };
                  }
                  return s;
                }),
              };
            });
          },
        }
      );
    } catch (err: any) {
      alert(`⚠️ Không thể kết nối API Gateway: ${err.message}.\nVui lòng đảm bảo các microservices đã được chạy.`);
    } finally {
      setIsLoading(false);
    }
  };

  // Helper to open policy viewer modal from any citation or document ID
  const handleOpenPolicyDoc = (docId: string, citations?: RetrievedDocument[]) => {
    const cleanId = docId.replace(/[\[\]\(\)]/g, '').trim().toUpperCase();
    const found = citations?.find((c) => c.doc_id.toUpperCase() === cleanId) ||
      copilotResponse?.citations?.find((c) => c.doc_id.toUpperCase() === cleanId);

    if (found) {
      setViewingPolicy(found);
    } else {
      setViewingPolicy({
        doc_id: cleanId,
        title: `Văn bản quy định [${cleanId}]`,
        content: `Tài liệu chính sách ${cleanId} của sàn thương mại điện tử Tiki.`,
        version: '2.0',
        is_active: true,
        policy_type: 'permanent',
        tags: [cleanId],
      });
    }
  };

  // Helper to parse markdown bold (**text**)
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
        <strong key={`${keyPrefix}-b-${bMatch.index}`} className="font-bold text-slate-900">
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

  // Helper function to render text with highlighted, clickable policy badges [POL-XXX] and markdown bold
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
          title={`Click để mở xem toàn văn bản quy định ${docCode}`}
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

  // Send message in active session
  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isLoading || !activeSession) return;

    const userText = inputQuery.trim();
    const currentSessionId = activeSession.sessionId;
    const nowTime = formatSystemTime();

    // 1. Create User Message
    const userMsgId = `usr_${Date.now()}`;
    const userMsg: ChatMessage = {
      id: userMsgId,
      role: 'customer',
      content: userText,
      timestamp: nowTime,
    };

    // Update title on first message
    const isFirstMsg = activeSession.messages.length === 0;
    const updatedTitle = isFirstMsg ? (userText.length > 28 ? `${userText.slice(0, 26)}...` : userText) : activeSession.title;

    // Save turn into persistent SQLite DB asynchronously
    apiClient.saveMessage(currentSessionId, 'customer', userText);

    if (!autoTriggerCopilot) {
      // Manual multi-line mode: Just post customer message into chat stream!
      setSessionsByCustomer((prev) => {
        const list = prev[selectedCustomerId] || [];
        const updated = list.map((s) => {
          if (s.sessionId === currentSessionId) {
            return {
              ...s,
              title: updatedTitle,
              messages: [...s.messages, userMsg],
              updatedAt: new Date().toISOString(),
            };
          }
          return s;
        });
        // Push active session to top
        const activeIdx = updated.findIndex((s) => s.sessionId === currentSessionId);
        if (activeIdx > 0) {
          const [moved] = updated.splice(activeIdx, 1);
          updated.unshift(moved);
        }
        return { ...prev, [selectedCustomerId]: updated };
      });
      setInputQuery('');
      return;
    }

    // Auto mode: Generate Immediate Contextual Buffer Acknowledgement ("CÂU CHỜ")
    let initialAck = 'Dạ em đã ghi nhận thông tin của anh/chị và đang kiểm tra hỗ trợ ngay đây ạ! Quý khách đợi em trong giây lát nhé...';
    const qLow = userText.toLowerCase();

    // Check specific topics in order of priority:
    if (qLow.includes('hủy') || qLow.includes('huy') || qLow.includes('cancel')) {
      initialAck = 'Dạ em đã nhận được yêu cầu hủy đơn hàng của mình. Em đang kiểm tra trạng thái kiện hàng và quy định hỗ trợ ngay đây ạ...';
    } else if (qLow.includes('đổi') || qLow.includes('doi') || qLow.includes('trả') || qLow.includes('tra') || qLow.includes('hoàn') || qLow.includes('hoan') || qLow.includes('refund')) {
      initialAck = 'Dạ Tiki đã ghi nhận yêu cầu về chính sách đổi trả / hoàn tiền. Em đang tra cứu quy định và dữ liệu đơn hàng cho mình ngay đây ạ...';
    } else if (qLow.includes('tiền') || qLow.includes('bao nhiêu') || qLow.includes('thanh toán') || qLow.includes('giá')) {
      initialAck = 'Dạ em đã ghi nhận thắc mắc về giá trị đơn hàng và thanh toán. Em đang kiểm tra bảng kê chi tiết gửi anh/chị ngay đây ạ!';
    } else if (qLow.includes('mã giảm') || qLow.includes('voucher') || qLow.includes('khuyến mãi') || qLow.includes('coupon') || qLow.includes('freeship')) {
      initialAck = 'Dạ em đã ghi nhận câu hỏi về mã giảm giá và ưu đãi của anh/chị. Em đang kiểm tra các chương trình khuyến mãi hiện hành ngay đây ạ!';
    } else if (qLow.includes('giao') || qLow.includes('ship') || qLow.includes('khi nào') || qLow.includes('bao giờ') || qLow.includes('vận đơn') || qLow.includes('lộ trình')) {
      initialAck = 'Dạ em đã ghi nhận câu hỏi về tiến độ giao hàng của anh/chị. Em đang kết nối tra cứu lộ trình vận chuyển ngay đây ạ!';
    } else if (qLow.includes('chào') || qLow.includes('hello') || qLow.includes('hi') || qLow.includes('alo')) {
      initialAck = 'Dạ Tiki chào anh/chị! Rất vui được hỗ trợ mình hôm nay. Anh/chị cần em hỗ trợ thông tin gì về đơn hàng hoặc chính sách mua sắm không ạ?';
    } else if (qLow.includes('thời tiết') || qLow.includes('phương trình') || qLow.includes('toán') || qLow.includes('ronaldo') || qLow.includes('ai')) {
      initialAck = 'Dạ em đã ghi nhận câu hỏi của anh/chị. Em đang kiểm tra thông tin để phản hồi ngay nhé ạ!';
    } else if (qLow.includes('ord-') || qLow.includes('đơn')) {
      initialAck = 'Dạ em đã ghi nhận câu hỏi về đơn hàng của anh/chị. Em đang kiểm tra hồ sơ hệ thống ngay đây ạ!';
    }

    const ackMsgId = `ack_${Date.now()}`;
    const ackMsg: ChatMessage = {
      id: ackMsgId,
      role: 'agent',
      content: initialAck,
      timestamp: nowTime,
      isAcknowledgement: true,
    };

    // OPTIMISTIC UPDATE: SHOW USER QUERY AND BUFFER ACK IMMEDIATELY (< 1ms)!
    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      const updated = list.map((s) => {
        if (s.sessionId === currentSessionId) {
          return {
            ...s,
            title: updatedTitle,
            messages: [...s.messages, userMsg, ackMsg],
            updatedAt: new Date().toISOString(),
          };
        }
        return s;
      });
      // Push active session to top
      const activeIdx = updated.findIndex((s) => s.sessionId === currentSessionId);
      if (activeIdx > 0) {
        const [moved] = updated.splice(activeIdx, 1);
        updated.unshift(moved);
      }
      return { ...prev, [selectedCustomerId]: updated };
    });

    setInputQuery('');
    apiClient.saveMessage(currentSessionId, 'acknowledgement', initialAck, true);

    // Call Copilot
    await triggerCopilotInference(userText, currentSessionId, ackMsgId);
  };

  // Manual Trigger: User has typed multiple messages and now clicks "Yêu cầu trả lời"
  const handleManualRequestResponse = async () => {
    if (isLoading || !activeSession) return;
    const currentSessionId = activeSession.sessionId;
    const nowTime = formatSystemTime();

    // Gather recent unresponded customer messages
    const recentCustomerMsgs: string[] = [];
    for (let i = activeSession.messages.length - 1; i >= 0; i--) {
      const m = activeSession.messages[i];
      if (m.role === 'customer') {
        recentCustomerMsgs.unshift(m.content);
      } else if (m.role === 'agent' && !m.isAcknowledgement) {
        break;
      }
    }

    const combinedQuery = recentCustomerMsgs.join(' \n ') || 'Yêu cầu hỗ trợ từ khách hàng';

    // Call dynamic fast acknowledgement from backend
    let initialAck = 'Dạ em đã nhận được đầy đủ thông tin của anh/chị. Em đang tổng hợp hồ sơ và chuẩn bị phản hồi chi tiết ngay nhé ạ!';
    try {
      const fastAckResp = await apiClient.getFastAck(combinedQuery, currentSessionId, currentCustomer.id);
      if (fastAckResp && fastAckResp.customer_acknowledgement) {
        initialAck = fastAckResp.customer_acknowledgement;
      }
    } catch (e) {
      // Fallback to local contextual ack
      if (combinedQuery.toLowerCase().includes('trả') || combinedQuery.toLowerCase().includes('hoàn')) {
        initialAck = 'Dạ em đã ghi nhận yêu cầu trả hàng và hoàn tiền của mình. Em đang tra cứu quy định và đơn hàng để hướng dẫn ngay ạ!';
      }
    }

    const ackMsgId = `ack_${Date.now()}`;
    const ackMsg: ChatMessage = {
      id: ackMsgId,
      role: 'agent',
      content: initialAck,
      timestamp: nowTime,
      isAcknowledgement: true,
    };

    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) => {
          if (s.sessionId === currentSessionId) {
            return {
              ...s,
              messages: [...s.messages, ackMsg],
              updatedAt: new Date().toISOString(),
            };
          }
          return s;
        }),
      };
    });

    apiClient.saveMessage(currentSessionId, 'acknowledgement', initialAck, true);
    await triggerCopilotInference(combinedQuery, currentSessionId, ackMsgId);
  };

  // Staff approves draft
  const handleApproveDraft = async () => {
    if (!activeSession || !activeSession.copilotResponse) return;
    const finalContent = activeSession.editedDraft.trim();
    if (!finalContent) return;

    const currentSessionId = activeSession.sessionId;
    const copilotResp = activeSession.copilotResponse;

    // Filter citations: ONLY attach policies that are EXPLICITLY referenced in finalContent (avoid legal risk)
    const citedMatches = finalContent.match(/POL-[A-Z0-9_-]+/gi) || [];
    const citedSet = new Set(citedMatches.map((c) => c.toUpperCase()));
    const activeCitations = (copilotResp.citations || []).filter((c) =>
      citedSet.has(c.doc_id.toUpperCase())
    );

    const agentMsg: ChatMessage = {
      id: `agent_${Date.now()}`,
      role: 'agent',
      content: finalContent,
      timestamp: formatSystemTime(),
      citations: activeCitations,
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
              updatedAt: new Date().toISOString(),
            };
          }
          return s;
        }),
      };
    });

    // Save final approved agent message to SQLite DB
    apiClient.saveMessage(currentSessionId, 'agent', finalContent, false);

    // Record review action to telemetry
    try {
      await apiClient.recordAction({
        interaction_id: copilotResp.interaction_id,
        action: 'APPROVE',
        final_text: finalContent,
        handling_time_ms: 2500,
      });
    } catch (err) {
      console.warn('Record action telemetry error:', err);
    }
  };

  // Staff updates draft text
  const handleUpdateDraft = (val: string) => {
    if (!activeSession) return;
    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) =>
          s.sessionId === activeSession.sessionId ? { ...s, editedDraft: val } : s
        ),
      };
    });
  };

  // Staff dismisses draft
  const handleDismissDraft = () => {
    if (!activeSession) return;
    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) =>
          s.sessionId === activeSession.sessionId ? { ...s, copilotResponse: null, editedDraft: '' } : s
        ),
      };
    });
  };

  // Copy policy text
  const handleCopyPolicy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedPolicy(true);
    setTimeout(() => setCopiedPolicy(false), 2000);
  };

  const messages = activeSession?.messages || [];
  const copilotResponse = activeSession?.copilotResponse;
  const editedDraft = activeSession?.editedDraft || '';

  // Check if there are customer messages waiting for response
  const lastMessage = messages[messages.length - 1];
  const hasUnrespondedCustomerMsg = lastMessage?.role === 'customer';

  // Dynamic components used for the recent request
  const componentsUsed = copilotResponse?.components_used || {};

  return (
    <div
      ref={containerRef}
      className="flex flex-col lg:flex-row h-[calc(100vh-135px)] w-full overflow-hidden select-text gap-0 relative"
    >
      {/* ------------------------------------------------------------- */}
      {/* COLUMN 1: Customer Profile & Session List (Resizable Left)    */}
      {/* ------------------------------------------------------------- */}
      <div
        style={{ width: `${leftWidth}px` }}
        className="flex-shrink-0 flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden"
      >
        {/* Customer Selector Dropdown */}
        <div className="p-3.5 border-b border-slate-100 bg-slate-50/70">
          <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 flex items-center justify-between">
            <span>Chọn Khách Hàng</span>
            <span className="text-[10px] text-blue-600 font-semibold bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100">
              Demo Users
            </span>
          </label>
          <select
            value={selectedCustomerId}
            onChange={(e) => handleSelectCustomer(e.target.value)}
            className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all cursor-pointer shadow-2xs"
          >
            {MOCK_CUSTOMERS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.id}) {c.orderId ? `• #${c.orderId}` : ''}
              </option>
            ))}
          </select>

          {/* Quick info card */}
          <div className="mt-2.5 p-2.5 bg-white rounded-xl border border-slate-200/80 text-[11px] space-y-1">
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
            className="flex items-center gap-1 px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-600 rounded-lg text-xs font-semibold transition-colors shadow-2xs cursor-pointer"
            title="Tạo cuộc hội thoại mới cho khách hàng này"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Mới</span>
          </button>
        </div>

        {/* Session List (Sorted newest first) */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {currentSessions.map((s) => {
            const isActive = s.sessionId === activeSessionId;
            const lastMsg = s.messages[s.messages.length - 1];
            const isEditing = editingSessionId === s.sessionId;

            return (
              <div
                key={s.sessionId}
                onClick={() => {
                  if (!isEditing) setActiveSessionId(s.sessionId);
                }}
                className={`p-2.5 rounded-xl cursor-pointer transition-all border group relative ${
                  isActive
                    ? 'bg-blue-50/80 border-blue-200 shadow-2xs'
                    : 'bg-white border-transparent hover:bg-slate-50 hover:border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  {isEditing ? (
                    <form
                      onSubmit={(e) => handleSaveRename(s.sessionId, e)}
                      onClick={(e) => e.stopPropagation()}
                      className="flex items-center gap-1 w-full"
                    >
                      <input
                        type="text"
                        value={tempTitle}
                        onChange={(e) => setTempTitle(e.target.value)}
                        className="w-full px-2 py-0.5 text-xs border border-blue-400 rounded bg-white focus:outline-none"
                        autoFocus
                      />
                      <button type="submit" className="p-1 text-emerald-600 hover:text-emerald-700 cursor-pointer" title="Lưu">
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingSessionId(null)}
                        className="p-1 text-slate-400 hover:text-slate-600 cursor-pointer"
                        title="Hủy"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </form>
                  ) : (
                    <>
                      <span
                        className={`text-xs font-semibold truncate flex-1 ${
                          isActive ? 'text-blue-900' : 'text-slate-700'
                        }`}
                        title={s.title}
                      >
                        {s.title}
                      </span>
                      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={(e) => handleStartRename(s, e)}
                          className="text-slate-400 hover:text-blue-600 p-0.5 transition-colors cursor-pointer"
                          title="Đổi tên hội thoại"
                        >
                          <Edit2 className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => handleDeleteSession(s.sessionId, e)}
                          className="text-slate-400 hover:text-red-500 p-0.5 transition-colors cursor-pointer"
                          title="Xóa phiên"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </>
                  )}
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

      {/* Resizer Splitter 1 (Left <-> Middle) */}
      <div
        onMouseDown={startDragLeft}
        className="hidden lg:flex w-2.5 hover:w-2.5 items-center justify-center cursor-col-resize group z-20 transition-colors mx-0.5 select-none"
        title="Kéo sang trái/phải để mở rộng hoặc thu hẹp thanh hội thoại"
      >
        <div className={`w-1 rounded-full transition-all ${isDraggingLeft ? 'bg-blue-600 h-20' : 'bg-slate-200 group-hover:bg-blue-400 h-8 group-hover:h-14'}`}></div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* COLUMN 2: Customer Dialogue Stream (Middle Panel)              */}
      {/* ------------------------------------------------------------- */}
      <div className="flex-1 min-w-[320px] flex flex-col bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
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
            className="text-xs text-slate-400 hover:text-slate-700 underline cursor-pointer"
          >
            Làm sạch tin nhắn
          </button>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 p-8">
              <MessageSquare className="w-12 h-12 mb-3 text-slate-300 stroke-[1.5]" />
              <p className="text-sm font-semibold text-slate-600">Bắt đầu phiên trò chuyện</p>
              <p className="text-xs mt-1 text-slate-400 max-w-xs">
                Đang hỗ trợ khách hàng <b>{currentCustomer.name}</b>. Khách hàng có thể nhập nhiều dòng mô tả trước khi yêu cầu Copilot soạn câu trả lời.
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
                  {/* Clickable and colored policy badges inside message content */}
                  <div className="leading-relaxed whitespace-pre-wrap">
                    {renderTextWithPolicyLinks(m.content, m.citations)}
                  </div>
                  {(() => {
                    if (!m.citations || m.citations.length === 0) return null;
                    // Only display citations that are actually cited inside m.content to avoid legal risk!
                    const citedMatches = m.content.match(/POL-[A-Z0-9_-]+/gi) || [];
                    const citedSet = new Set(citedMatches.map((c) => c.toUpperCase()));
                    const activeCitations = m.citations.filter((c) => citedSet.has(c.doc_id.toUpperCase()));
                    if (activeCitations.length === 0) return null;

                    return (
                      <div className="mt-2.5 pt-2 border-t border-slate-200/60 text-[11px] text-slate-500">
                        <span className="font-semibold block mb-1">📚 Căn cứ chính sách:</span>
                        <div className="flex flex-wrap gap-1.5">
                          {activeCitations.map((c) => (
                            <button
                              key={c.doc_id}
                              type="button"
                              onClick={() => handleOpenPolicyDoc(c.doc_id, m.citations)}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 text-[10px] font-medium cursor-pointer transition-colors"
                            >
                              <FileText className="w-3 h-3 text-blue-500" />
                              <span>[{c.doc_id}] {c.title}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
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

        {/* E-commerce Multi-message Banner & Trigger Button */}
        {hasUnrespondedCustomerMsg && !isLoading && !copilotResponse && (
          <div className="px-4 py-2 bg-blue-50/90 border-t border-blue-100 flex items-center justify-between">
            <span className="text-[11px] text-blue-700">
              Khách đã gửi tin. Bạn có thể gửi thêm dòng hoặc yêu cầu Copilot soạn trả lời ngay:
            </span>
            <button
              onClick={handleManualRequestResponse}
              className="flex items-center gap-1.5 px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold transition-all shadow-xs cursor-pointer animate-pulse"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>⚡ Yêu cầu trả lời</span>
            </button>
          </div>
        )}

        {/* Input Bar with Auto-trigger Toggle */}
        <div className="p-3 border-t border-slate-100 bg-white space-y-2">
          <div className="flex items-center justify-between text-[11px] text-slate-500 px-1">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={autoTriggerCopilot}
                onChange={(e) => setAutoTriggerCopilot(e.target.checked)}
                className="rounded text-blue-600 focus:ring-blue-500 cursor-pointer"
              />
              <span className="font-medium text-slate-600">
                Tự động yêu cầu Copilot phản hồi khi gửi (dành cho câu hỏi đơn)
              </span>
            </label>
            {!autoTriggerCopilot && (
              <span className="text-amber-600 text-[10px] font-semibold bg-amber-50 px-2 py-0.5 rounded">
                Chế độ nhập nhiều dòng
              </span>
            )}
          </div>

          <form onSubmit={handleSend} className="flex gap-2">
            <input
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              placeholder={
                autoTriggerCopilot
                  ? `Nhập câu hỏi từ khách hàng ${currentCustomer.name}...`
                  : `Nhập dòng tin nhắn của khách hàng (bấm gửi rồi bấm 'Yêu cầu trả lời')...`
              }
              disabled={isLoading || !activeSession}
              className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 disabled:bg-slate-50"
            />
            <button
              type="submit"
              disabled={isLoading || !inputQuery.trim() || !activeSession}
              className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1.5 cursor-pointer shadow-sm"
              title={autoTriggerCopilot ? 'Gửi câu hỏi và kích hoạt Copilot' : 'Gửi tin nhắn này vào khung chat'}
            >
              {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              <span>{autoTriggerCopilot ? 'Gửi & Trả lời' : 'Gửi dòng tin'}</span>
            </button>
            {!autoTriggerCopilot && (
              <button
                type="button"
                onClick={handleManualRequestResponse}
                disabled={isLoading || activeSession.messages.length === 0}
                className="px-3.5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1 cursor-pointer shadow-sm"
                title="Yêu cầu Copilot tổng hợp các tin nhắn trên và soạn bản nháp"
              >
                <Zap className="w-4 h-4" />
                <span>Yêu cầu trả lời</span>
              </button>
            )}
          </form>
        </div>
      </div>

      {/* Resizer Splitter 2 (Middle <-> Right) */}
      <div
        onMouseDown={startDragRight}
        className="hidden lg:flex w-2.5 hover:w-2.5 items-center justify-center cursor-col-resize group z-20 transition-colors mx-0.5 select-none"
        title="Kéo sang trái/phải để mở rộng hoặc thu hẹp khung làm việc Copilot"
      >
        <div className={`w-1 rounded-full transition-all ${isDraggingRight ? 'bg-blue-600 h-20' : 'bg-slate-200 group-hover:bg-blue-400 h-8 group-hover:h-14'}`}></div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* COLUMN 3: Copilot CS Support & Draft Editor (Resizable Right) */}
      {/* ------------------------------------------------------------- */}
      <div
        style={{ width: `${rightWidth}px` }}
        className="flex-shrink-0 flex flex-col space-y-4 overflow-y-auto"
      >
        {copilotResponse ? (
          <>
            {/* Guardrail & Classification Analysis Card */}
            <Card title="🛡️ Phân tích Thông minh từ Copilot">
              <div className="space-y-2.5 text-xs">
                <div className="flex items-center justify-between pb-1.5 border-b border-slate-100">
                  <span className="text-slate-500">Ý định phân loại:</span>
                  <Badge variant="info">{copilotResponse.intent?.intent || 'out_of_scope'}</Badge>
                </div>

                <div className="flex items-center justify-between pb-1.5 border-b border-slate-100">
                  <span className="text-slate-500">Loại đầu vào:</span>
                  <span className="font-semibold text-slate-700">{copilotResponse.input_type || 'new_question'}</span>
                </div>

                <div className="flex items-center justify-between pb-1.5 border-b border-slate-100">
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
                    {copilotResponse.guardrail?.action_type || 'PROCEED_TO_LLM'}
                  </Badge>
                </div>

                {/* Dynamic System Components Used in the Most Recent Request */}
                <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-100 space-y-1.5 text-[11px]">
                  <span className="font-bold text-slate-700 block mb-1 flex items-center justify-between">
                    <span>⚙️ Thành phần Hệ thống đang dùng:</span>
                    <span className="text-[10px] text-emerald-600 font-semibold bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-100">
                      Request gần nhất
                    </span>
                  </span>
                  <div className="flex justify-between items-start text-slate-600">
                    <span className="font-medium text-slate-500">• Phân loại Intent:</span>
                    <span className="font-semibold text-slate-800 text-right max-w-[210px]">
                      {componentsUsed.intent_classifier || 'Hybrid NLU (Quy tắc & Semantic Rules)'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start text-slate-600">
                    <span className="font-medium text-slate-500">• Tiền xử lý Ngữ cảnh:</span>
                    <span className="font-semibold text-blue-600 text-right max-w-[210px]">
                      {componentsUsed.query_rewriter || 'LLM Contextual Query Rewriter'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start text-slate-600">
                    <span className="font-medium text-slate-500">• Tra cứu RAG:</span>
                    <span className="font-semibold text-slate-800 text-right max-w-[210px]">
                      {componentsUsed.retrieval_engine || 'BM25 + Semantic Vector Retrieval'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start text-slate-600">
                    <span className="font-medium text-slate-500">• Sinh Bản nháp:</span>
                    <span className="font-semibold text-emerald-700 text-right max-w-[210px]">
                      {componentsUsed.draft_engine || 'Mô hình LLM gpt-oss (openai-gpt-oss-20b)'}
                    </span>
                  </div>
                  <div className="flex justify-between items-start text-slate-600">
                    <span className="font-medium text-slate-500">• Chốt chặn An toàn:</span>
                    <span className="font-semibold text-slate-800 text-right max-w-[210px]">
                      {componentsUsed.safety_envelope || 'NLI Faithfulness & Financial Hard Gate'}
                    </span>
                  </div>
                </div>

                {/* Collapsible Details */}
                <div>
                  <button
                    onClick={() => setShowAnalysisDetails(!showAnalysisDetails)}
                    className="flex items-center justify-between w-full text-[11px] font-semibold text-blue-600 hover:text-blue-700 pt-1 cursor-pointer"
                  >
                    <span>{showAnalysisDetails ? 'Thu gọn chi tiết phân tích' : 'Xem thêm chi tiết kiểm định an toàn'}</span>
                    {showAnalysisDetails ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>

                  {showAnalysisDetails && (
                    <div className="mt-2 p-2.5 bg-slate-50 rounded-lg border border-slate-100 space-y-1.5 text-[11px] text-slate-600">
                      {copilotResponse.rewritten_query && (
                        <p className="bg-white p-2 rounded border border-blue-100 text-blue-900">
                          <b>Truy vấn đã bổ sung ngữ cảnh:</b> "{copilotResponse.rewritten_query}"
                        </p>
                      )}
                      <p className="italic">
                        <b>Lý do Guardrail:</b> "{copilotResponse.guardrail?.reason}"
                      </p>
                      {copilotResponse.guardrail?.temporal_status && (
                        <p>
                          <b>Trạng thái Hiệu lực:</b> {copilotResponse.guardrail.temporal_status}
                        </p>
                      )}
                      <p>
                        <b>ID tương tác:</b> <span className="font-mono text-[10px]">{copilotResponse.interaction_id}</span>
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </Card>

            {/* Dynamic Order Card (Module 3) */}
            {copilotResponse.order_data && (
              <Card title="📦 Tra cứu Đơn hàng (Dynamic Tool Calling)">
                <div className="p-3 bg-blue-50/50 rounded-xl border border-blue-100 text-xs space-y-1.5">
                  <div className="flex justify-between font-semibold text-slate-800">
                    <span>Mã đơn: #{copilotResponse.order_data.order_id}</span>
                    <Badge variant="info">{copilotResponse.order_data.order_status || copilotResponse.order_data.status}</Badge>
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
                  {copilotResponse.order_data.estimated_delivery && (
                    <p className="text-slate-500">
                      Giao hàng: {copilotResponse.order_data.estimated_delivery} ({copilotResponse.order_data.carrier || 'Tiki Delivery'})
                    </p>
                  )}
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

              {/* Mode switch tabs: Preview vs Edit */}
              <div className="mb-2 flex flex-wrap items-center justify-between gap-1.5 border-b border-slate-100 pb-2">
                <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg text-xs shrink-0">
                  <button
                    type="button"
                    onClick={() => setDraftMode('preview')}
                    className={`px-2 py-1 rounded-md font-semibold transition-all cursor-pointer flex items-center gap-1 whitespace-nowrap ${
                      draftMode === 'preview'
                        ? 'bg-white text-blue-700 shadow-2xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <Eye className="w-3 h-3" />
                    <span>Xem bản thảo</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraftMode('edit')}
                    className={`px-2 py-1 rounded-md font-semibold transition-all cursor-pointer flex items-center gap-1 whitespace-nowrap ${
                      draftMode === 'edit'
                        ? 'bg-white text-blue-700 shadow-2xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <Edit2 className="w-3 h-3" />
                    <span>Chỉnh sửa</span>
                  </button>
                </div>
                <span className="text-[10px] text-slate-400 font-medium whitespace-nowrap">
                  {draftMode === 'preview' ? 'Nhấp POL để tra cứu' : 'Sửa trực tiếp'}
                </span>
              </div>

              {draftMode === 'preview' ? (
                /* Interactive preview with clickable policy tags (Only 1 box shown!) */
                <div className="mb-2.5 p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs leading-relaxed max-h-56 overflow-y-auto whitespace-pre-wrap text-slate-800 font-sans shadow-inner">
                  {renderTextWithPolicyLinks(editedDraft, copilotResponse.citations)}
                </div>
              ) : (
                /* Edit Mode: Textarea */
                <textarea
                  value={editedDraft}
                  onChange={(e) => handleUpdateDraft(e.target.value)}
                  rows={6}
                  className="w-full mb-2.5 p-3 rounded-xl border border-blue-400 ring-2 ring-blue-500/10 text-xs leading-relaxed focus:outline-none font-sans"
                  placeholder="Nội dung bản nháp..."
                  autoFocus
                />
              )}

              <div className="mt-2 flex gap-2">
                <button
                  onClick={handleApproveDraft}
                  className="flex-1 py-2 px-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors shadow-sm cursor-pointer"
                >
                  <CheckCircle className="w-4 h-4" />
                  <span>Duyệt & Gửi Khách Hàng</span>
                </button>
                <button
                  onClick={handleDismissDraft}
                  className="py-2 px-3 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition-colors cursor-pointer"
                >
                  Bỏ qua
                </button>
              </div>
            </Card>

            {/* Citations List with "Xem văn bản" button */}
            {copilotResponse.citations && copilotResponse.citations.length > 0 && (
              <Card title="📚 Căn cứ Chính sách Trích xuất">
                <div className="space-y-2 text-xs">
                  {copilotResponse.citations.map((c) => (
                    <div
                      key={c.doc_id}
                      id={`policy-card-${c.doc_id}`}
                      className="p-2.5 bg-slate-50 rounded-lg border border-slate-100 transition-colors"
                    >
                      <div className="flex items-center justify-between font-semibold text-slate-800 mb-1.5">
                        <span className="truncate max-w-[190px]">[{c.doc_id}] {c.title}</span>
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => setViewingPolicy(c)}
                            className="flex items-center gap-1 text-[11px] text-blue-600 hover:text-blue-700 font-semibold bg-blue-50 hover:bg-blue-100 px-2 py-0.5 rounded border border-blue-200 transition-colors cursor-pointer"
                            title="Mở toàn văn bản chính sách này"
                          >
                            <FileText className="w-3 h-3" />
                            <span>Xem văn bản</span>
                          </button>
                          <Badge variant={c.is_active ? 'success' : 'danger'}>
                            {c.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </div>
                      </div>
                      <p className="text-slate-600 line-clamp-2 text-[11px]">{c.content}</p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </>
        ) : isLoading ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-8 bg-white rounded-2xl border border-blue-200/80 shadow-xs">
            <div className="w-12 h-12 mb-3 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center animate-pulse">
              <Bot className="w-6 h-6 animate-bounce" />
            </div>
            <p className="text-sm font-bold text-slate-800">Copilot đang soạn thảo bản nháp...</p>
            <p className="text-xs mt-1 text-slate-500 max-w-xs">
              Đang phân tích ý định, tra cứu RAG và kiểm định an toàn tài chính. Câu đệm đã được gửi tức thì cho khách hàng!
            </p>
            <div className="mt-4 flex items-center gap-2 text-[11px] text-blue-600 font-semibold bg-blue-50 px-3 py-1.5 rounded-full border border-blue-100">
              <span className="w-2 h-2 rounded-full bg-blue-600 animate-ping"></span>
              <span>Đang kết nối LLM ({currentCustomer.name})</span>
            </div>
          </div>
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

      {/* Policy Document Inspection Modal */}
      {viewingPolicy && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-600" />
                <div>
                  <h3 className="text-sm font-bold text-slate-800">[{viewingPolicy.doc_id}] {viewingPolicy.title}</h3>
                  <span className="text-[11px] text-slate-400">Văn bản quy định chính sách thương mại điện tử Tiki</span>
                </div>
              </div>
              <button
                onClick={() => setViewingPolicy(null)}
                className="text-slate-400 hover:text-slate-600 text-sm font-bold p-1 cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="flex items-center justify-between py-1 px-3 bg-slate-50 rounded-xl text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-500">Trạng thái hiệu lực:</span>
                <Badge variant={viewingPolicy.is_active ? 'success' : 'danger'}>
                  {viewingPolicy.is_active ? 'Đang hiệu lực (ACTIVE)' : 'Hết hiệu lực (INACTIVE)'}
                </Badge>
              </div>
              <button
                onClick={() => handleCopyPolicy(viewingPolicy.content)}
                className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-semibold cursor-pointer"
              >
                {copiedPolicy ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedPolicy ? 'Đã sao chép!' : 'Sao chép văn bản'}</span>
              </button>
            </div>

            <div>
              <span className="text-xs font-bold text-slate-700 block mb-1">Toàn văn tài liệu:</span>
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 max-h-80 overflow-y-auto whitespace-pre-wrap text-xs text-slate-700 leading-relaxed font-sans">
                {viewingPolicy.content}
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setViewingPolicy(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold cursor-pointer transition-colors"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
