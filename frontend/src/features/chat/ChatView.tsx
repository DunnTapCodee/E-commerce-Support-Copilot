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
  CornerUpLeft,
} from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { CustomerOrderRecord, CustomerProfileRecord, GatewayResponse, RetrievedDocument } from '../../types';
import { formatSystemTime } from '../../lib/time';

export interface ChatMessage {
  id: string;
  role: 'customer' | 'agent' | 'system' | 'acknowledgement';
  content: string;
  timestamp: string;
  citations?: RetrievedDocument[];
  isAcknowledgement?: boolean;
}

export interface CustomerProfile {
  id: string;
  name: string;
  phone: string;
  email?: string;
  assignedStaffId?: string;
  orderId?: string;
  orderStatus?: string;
}

export const MOCK_CUSTOMERS: CustomerProfile[] = [
  {
    id: 'CUST-1100',
    name: 'Lê Văn Sơn',
    phone: '0998.708.581',
    assignedStaffId: 'staff-01',
    orderId: 'ORD-1100',
    orderStatus: 'Đã giao hàng (DELIVERED)',
  },
  {
    id: 'CUST-1002',
    name: 'Phan Văn An',
    phone: '0974.716.127',
    assignedStaffId: 'staff-02',
    orderId: 'ORD-1002',
    orderStatus: 'Đang vận chuyển (SHIPPING)',
  },
  {
    id: 'CUST-1001',
    name: 'Bùi Thị An',
    phone: '0938.242.854',
    assignedStaffId: 'staff-01',
    orderId: 'ORD-1001',
    orderStatus: 'Chờ giao hàng (PROCESSING)',
  },
  {
    id: 'CUST-1003',
    name: 'Vũ Thanh Linh',
    phone: '0999.532.448',
    assignedStaffId: 'staff-03',
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
  messageCount?: number;
}

interface ChatViewProps {
  selectedStaffId?: string;
  selectedStaffName?: string;
  initialCustomerId?: string;
  initialSessionId?: string;
}

export const ChatView: React.FC<ChatViewProps> = ({
  selectedStaffId,
  selectedStaffName,
  initialCustomerId,
  initialSessionId,
}) => {
  // Live customers list loaded from backend DB
  const [allCustomers, setAllCustomers] = useState<CustomerProfile[]>(MOCK_CUSTOMERS);
  const [filterByStaff, setFilterByStaff] = useState<boolean>(false);
  const [customerOrders, setCustomerOrders] = useState<CustomerOrderRecord[]>([]);
  const [showOrdersDrawer, setShowOrdersDrawer] = useState<boolean>(false);

  // Selected customer state synchronized with localStorage ('copilot_selected_cust')
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>(() => {
    return initialCustomerId || localStorage.getItem('copilot_selected_cust') || 'CUST-1100';
  });

  // Customer sessions map: customerId -> ConversationSession[] (SQLite is source of truth)
  const [sessionsByCustomer, setSessionsByCustomer] = useState<Record<string, ConversationSession[]>>({});

  // Active session ID
  const [activeSessionId, setActiveSessionId] = useState<string>(initialSessionId || '');

  const [inputQuery, setInputQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  // Input mode in Staff Chat Bar: 'staff_reply' (Staff replies directly) vs 'simulate_customer' (Test customer ask + Copilot)
  const [chatInputMode, setChatInputMode] = useState<'staff_reply' | 'simulate_customer'>('simulate_customer');

  // E-commerce multi-message: Toggle auto-request vs manual "Yêu cầu trả lời"
  const [autoTriggerCopilot, setAutoTriggerCopilot] = useState<boolean>(true);

  // Rename session inline state
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [tempTitle, setTempTitle] = useState('');

  // Policy modal viewer state
  const [viewingPolicy, setViewingPolicy] = useState<RetrievedDocument | null>(null);
  const [copiedPolicy, setCopiedPolicy] = useState(false);
  const [allPolicies, setAllPolicies] = useState<RetrievedDocument[]>([]);

  // Customer activity map (customerId -> latest session activity) to sort customers with newest questions first
  const [customerActivity, setCustomerActivity] = useState<
    Record<string, { updatedAt: string; hasPendingDraft: boolean; lastTitle: string; messageCount: number }>
  >({});

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

  // Sync selected customer when initialCustomerId / initialSessionId prop changes
  useEffect(() => {
    if (initialCustomerId) {
      setSelectedCustomerId(initialCustomerId);
    }
    if (initialSessionId) {
      setActiveSessionId(initialSessionId);
    }
  }, [initialCustomerId, initialSessionId]);

  // Load live customers from backend database
  useEffect(() => {
    let mounted = true;
    const loadCustomersFromDb = async () => {
      try {
        const dbCusts: CustomerProfileRecord[] = await apiClient.listCustomers();
        if (mounted && dbCusts && dbCusts.length > 0) {
          const mapped: CustomerProfile[] = dbCusts.map((c) => {
            const mockMatch = MOCK_CUSTOMERS.find((m) => m.id === c.customer_id);
            return {
              id: c.customer_id,
              name: c.name,
              phone: c.phone || mockMatch?.phone || '',
              email: c.email || undefined,
              assignedStaffId: c.assigned_staff_id || mockMatch?.assignedStaffId,
              orderId: mockMatch?.orderId,
              orderStatus: mockMatch?.orderStatus,
            };
          });
          setAllCustomers(mapped);
        }
      } catch (e) {
        console.warn('Load customers error:', e);
      }
    };
    loadCustomersFromDb();
    apiClient
      .listPolicies()
      .then((pols) => {
        if (mounted && Array.isArray(pols)) {
          setAllPolicies(pols);
        }
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  // Helper to refresh activity across all customers so newest questions float to the top
  const refreshAllCustomerActivity = React.useCallback(async () => {
    try {
      const allSess = await apiClient.listSessions();
      if (!Array.isArray(allSess)) return;
      const map: Record<string, { updatedAt: string; hasPendingDraft: boolean; lastTitle: string; messageCount: number }> = {};
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
            messageCount: s.messageCount || 0,
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
          existing.messageCount += s.messageCount || 0;
        }
      }
      setCustomerActivity(map);
    } catch (e) {
      // ignore
    }
  }, []);

  useEffect(() => {
    refreshAllCustomerActivity();
  }, [refreshAllCustomerActivity]);

  // Filter and sort customer list: customers with pending questions / newest activity appear at the TOP
  const displayedCustomers = React.useMemo(() => {
    let base = allCustomers;
    if (filterByStaff && selectedStaffId) {
      const filtered = allCustomers.filter((c) => c.assignedStaffId === selectedStaffId);
      if (filtered.length > 0) base = filtered;
    }
    return [...base].sort((a, b) => {
      const actA = customerActivity[a.id];
      const actB = customerActivity[b.id];
      // 1. Customers with a pending Copilot draft / unanswered question come first
      if (actA?.hasPendingDraft && !actB?.hasPendingDraft) return -1;
      if (!actA?.hasPendingDraft && actB?.hasPendingDraft) return 1;
      // 2. Sort by most recent question/session updatedAt timestamp descending
      const timeA = actA?.updatedAt ? new Date(actA.updatedAt).getTime() : 0;
      const timeB = actB?.updatedAt ? new Date(actB.updatedAt).getTime() : 0;
      if (timeA !== timeB) return timeB - timeA;
      return 0;
    });
  }, [allCustomers, filterByStaff, selectedStaffId, customerActivity]);

  useEffect(() => {
    localStorage.setItem('copilot_selected_cust', selectedCustomerId);
  }, [selectedCustomerId]);

  // Load customer orders whenever selectedCustomerId changes
  useEffect(() => {
    if (!selectedCustomerId) return;
    let mounted = true;
    const loadOrders = async () => {
      try {
        const orders = await apiClient.getCustomerOrders(selectedCustomerId);
        if (mounted) {
          setCustomerOrders((orders as CustomerOrderRecord[]) || []);
        }
      } catch (e) {
        console.warn('Load customer orders error:', e);
      }
    };
    loadOrders();
    return () => {
      mounted = false;
    };
  }, [selectedCustomerId]);

  // Load persistent sessions from backend SQLite database on mount / customer switch
  useEffect(() => {
    if (!selectedCustomerId) return;
    let isMounted = true;
    const loadBackendSessions = async () => {
      try {
        const dbSessions = await apiClient.listSessions(selectedCustomerId);
        if (!isMounted) return;

        if (dbSessions && dbSessions.length > 0) {
          setSessionsByCustomer((prev) => {
            const currentList = prev[selectedCustomerId] || [];
            const existingMap = new Map<string, ConversationSession>();
            currentList.forEach((s) => existingMap.set(s.sessionId, s));

            const syncedList: ConversationSession[] = dbSessions.map((ds: any) => {
              const prevSess = existingMap.get(ds.sessionId);
              return {
                sessionId: ds.sessionId,
                customerId: ds.customerId,
                title: ds.title || prevSess?.title || 'Hội thoại mới',
                createdAt: ds.createdAt ? formatSystemTime(ds.createdAt) : prevSess?.createdAt || formatSystemTime(),
                updatedAt: ds.updatedAt || prevSess?.updatedAt || new Date().toISOString(),
                messages: prevSess?.messages || [],
                copilotResponse: prevSess?.copilotResponse || null,
                editedDraft: ds.copilotDraft ?? prevSess?.editedDraft ?? '',
                messageCount: ds.messageCount ?? prevSess?.messages.length ?? 0,
              };
            });

            return {
              ...prev,
              [selectedCustomerId]: syncedList,
            };
          });

          setActiveSessionId((curr) => {
            if (initialSessionId && dbSessions.some((s: any) => s.sessionId === initialSessionId)) {
              return initialSessionId;
            }
            if (curr && dbSessions.some((s: any) => s.sessionId === curr)) {
              return curr;
            }
            return dbSessions[0].sessionId;
          });
        } else {
          // No session in SQLite yet for this customer -> create one in SQLite
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
            messageCount: 0,
          };
          setSessionsByCustomer((prev) => ({
            ...prev,
            [selectedCustomerId]: [newSession],
          }));
          setActiveSessionId(newSessId);
          await apiClient.createSession(newSessId, selectedCustomerId, 'Hội thoại mới');
        }
      } catch (err) {
        console.warn('Load backend sessions error:', err);
      }
    };
    loadBackendSessions();
    return () => {
      isMounted = false;
    };
  }, [selectedCustomerId, initialSessionId]);

  // Real-time synchronization of active session history & Copilot draft from SQLite (on change + every 2.5s)
  const syncSessionFromSqlite = async (manual = false) => {
    if (!activeSessionId || !selectedCustomerId) return;
    if (isLoading && !manual) return;
    if (manual) setIsSyncing(true);
    try {
      const [dbSessions, details] = await Promise.all([
        apiClient.listSessions(selectedCustomerId),
        apiClient.getSessionDetails(activeSessionId),
      ]);
      // Also refresh global customer activity so newest customer questions float to top of list
      refreshAllCustomerActivity();

      setSessionsByCustomer((prev) => {
        const currentList = prev[selectedCustomerId] || [];
        const existingMap = new Map<string, ConversationSession>();
        currentList.forEach((s) => existingMap.set(s.sessionId, s));

        let baseList = currentList;
        if (dbSessions && dbSessions.length > 0) {
          baseList = dbSessions.map((ds: any) => {
            const prevSess = existingMap.get(ds.sessionId);
            return {
              sessionId: ds.sessionId,
              customerId: ds.customerId,
              title: ds.title || prevSess?.title || 'Hội thoại mới',
              createdAt: ds.createdAt ? formatSystemTime(ds.createdAt) : prevSess?.createdAt || formatSystemTime(),
              updatedAt: ds.updatedAt || prevSess?.updatedAt || new Date().toISOString(),
              messages: prevSess?.messages || [],
              copilotResponse: prevSess?.copilotResponse || null,
              editedDraft: prevSess?.editedDraft || ds.copilotDraft || '',
              messageCount: ds.messageCount ?? prevSess?.messages.length ?? 0,
            };
          });
        }

        if (details) {
          baseList = baseList.map((s) => {
            if (s.sessionId === activeSessionId) {
              const nextDraft =
                draftMode === 'edit' && s.editedDraft
                  ? s.editedDraft
                  : details.copilotDraft !== undefined
                    ? details.copilotDraft
                    : s.editedDraft;
              return {
                ...s,
                title: details.title || s.title,
                messages: Array.isArray(details.messages) ? details.messages : s.messages,
                editedDraft: nextDraft,
                copilotResponse:
                  details.copilotResponse !== undefined ? details.copilotResponse : s.copilotResponse,
                messageCount: Array.isArray(details.messages) ? details.messages.length : s.messageCount,
              };
            }
            return s;
          });
        }

        return {
          ...prev,
          [selectedCustomerId]: baseList,
        };
      });
    } catch (err) {
      console.warn('Sync session history error:', err);
    } finally {
      if (manual) setIsSyncing(false);
    }
  };

  useEffect(() => {
    if (!activeSessionId || !selectedCustomerId) return;
    syncSessionFromSqlite(false);
    const timer = setInterval(() => {
      syncSessionFromSqlite(false);
    }, 2500);
    return () => clearInterval(timer);
  }, [activeSessionId, selectedCustomerId, isLoading, draftMode]);

  // Active customer helper
  const currentCustomer =
    allCustomers.find((c) => c.id === selectedCustomerId) ||
    MOCK_CUSTOMERS.find((c) => c.id === selectedCustomerId) ||
    allCustomers[0] ||
    MOCK_CUSTOMERS[0];

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
      setActiveSessionId('');
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
    const found =
      citations?.find((c) => c.doc_id.toUpperCase() === cleanId) ||
      copilotResponse?.citations?.find((c) => c.doc_id.toUpperCase() === cleanId) ||
      allPolicies.find((p) => p.doc_id.toUpperCase() === cleanId);

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

  // Find the customer question that a given agent/acknowledgement message is replying to (Messenger-style quote)
  const findRepliedCustomerQuestion = (msgs: ChatMessage[], currentIdx: number): ChatMessage | null => {
    for (let i = currentIdx - 1; i >= 0; i--) {
      if (msgs[i].role === 'customer') {
        return msgs[i];
      }
    }
    return null;
  };

  // Helper to parse markdown bold (**text**)
  const parseMarkdownBold = (rawText: string, keyPrefix: string, isDarkBubble = false) => {
    const boldRegex = /\*\*([^*]+)\*\*/g;
    const nodes: (string | React.ReactNode)[] = [];
    let lastIdx = 0;
    let bMatch: RegExpExecArray | null;

    while ((bMatch = boldRegex.exec(rawText)) !== null) {
      if (bMatch.index > lastIdx) {
        nodes.push(rawText.slice(lastIdx, bMatch.index));
      }
      nodes.push(
        <strong
          key={`${keyPrefix}-b-${bMatch.index}`}
          className={isDarkBubble ? 'font-bold text-white underline decoration-blue-200/60' : 'font-bold text-slate-900'}
        >
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
  const renderTextWithPolicyLinks = (
    text: string,
    citations?: RetrievedDocument[],
    isDarkBubble = false
  ) => {
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
        parts.push(...parseMarkdownBold(textChunk, `pre-${matchStart}`, isDarkBubble));
      }

      parts.push(
        <button
          key={`policy-${matchStart}-${docCode}`}
          type="button"
          onClick={() => handleOpenPolicyDoc(docCode, citations)}
          className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 mx-0.5 rounded-md font-mono text-[11px] font-bold cursor-pointer transition-colors shadow-2xs align-baseline ${
            isDarkBubble
              ? 'text-blue-700 bg-white hover:bg-blue-50 border border-blue-200'
              : 'text-blue-700 bg-blue-100 hover:bg-blue-200 border border-blue-300/80'
          }`}
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
      parts.push(...parseMarkdownBold(textChunk, `post-${lastIndex}`, isDarkBubble));
    }

    return parts;
  };

  // Send message in active session (supports both Direct Staff Reply and Customer Simulation)
  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || isLoading || !activeSession) return;

    const userText = inputQuery.trim();
    const currentSessionId = activeSession.sessionId;
    const nowTime = formatSystemTime();

    // MODE 1: Staff replies directly to the customer
    if (chatInputMode === 'staff_reply') {
      const staffMsg: ChatMessage = {
        id: `agent_${Date.now()}`,
        role: 'agent',
        content: userText,
        timestamp: nowTime,
        isAcknowledgement: false,
      };

      setSessionsByCustomer((prev) => {
        const list = prev[selectedCustomerId] || [];
        return {
          ...prev,
          [selectedCustomerId]: list.map((s) =>
            s.sessionId === currentSessionId
              ? {
                  ...s,
                  messages: [...s.messages, staffMsg],
                  copilotResponse: null,
                  editedDraft: '',
                  updatedAt: new Date().toISOString(),
                }
              : s
          ),
        };
      });
      setInputQuery('');
      await apiClient.saveMessage(currentSessionId, 'agent', userText, false, selectedCustomerId);
      return;
    }

    // MODE 2: Simulate Customer message (Test Copilot directly in Staff Workbench)
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
    apiClient.saveMessage(currentSessionId, 'customer', userText, false, selectedCustomerId);

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
    if (!activeSession) return;
    const finalContent = activeSession.editedDraft.trim();
    if (!finalContent) return;

    const currentSessionId = activeSession.sessionId;
    const copilotResp = activeSession.copilotResponse;

    // Filter citations: ONLY attach policies that are EXPLICITLY referenced in finalContent (avoid legal risk)
    const citedMatches = finalContent.match(/POL-[A-Z0-9_-]+/gi) || [];
    const citedSet = new Set(citedMatches.map((c) => c.toUpperCase()));
    const activeCitations = (copilotResp?.citations || []).filter((c) =>
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

    // Save final approved agent message to SQLite DB (also clears copilot_draft in SQLite)
    await apiClient.saveMessage(currentSessionId, 'agent', finalContent, false, selectedCustomerId);

    // Record review action to telemetry
    if (copilotResp?.interaction_id) {
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
    const sessId = activeSession.sessionId;
    setSessionsByCustomer((prev) => {
      const list = prev[selectedCustomerId] || [];
      return {
        ...prev,
        [selectedCustomerId]: list.map((s) =>
          s.sessionId === sessId ? { ...s, copilotResponse: null, editedDraft: '' } : s
        ),
      };
    });
    apiClient.clearSessionDraft(sessId);
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
  const hasPendingCopilot = Boolean(copilotResponse || editedDraft.trim());

  // Check if there are customer messages waiting for response (including when Customer sent a message on /customer and got an ack)
  const lastMessage = messages[messages.length - 1];
  const hasUnrespondedCustomerMsg =
    lastMessage?.role === 'customer' ||
    lastMessage?.role === 'acknowledgement' ||
    Boolean(lastMessage?.isAcknowledgement);

  // Dynamic components used for the recent request
  const componentsUsed = copilotResponse?.components_used || {};
  const latestCustomerOrder = customerOrders[0];

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
        {/* Customer Selector & Priority Queue (Newest Questions First) */}
        <div className="p-3.5 border-b border-slate-100 bg-slate-50/70">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Khách Hàng (Mới nhất lên đầu)
            </span>
            {selectedStaffId && (
              <button
                type="button"
                onClick={() => setFilterByStaff((v) => !v)}
                className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors cursor-pointer ${
                  filterByStaff
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : 'bg-blue-50 text-blue-600 border-blue-100 hover:bg-blue-100'
                }`}
                title="Bấm để chuyển đổi giữa danh sách khách phụ trách riêng hoặc toàn bộ khách hàng"
              >
                {filterByStaff ? `Phụ trách (${displayedCustomers.length})` : `Tất cả (${allCustomers.length})`}
              </button>
            )}
          </div>
          <select
            value={selectedCustomerId}
            onChange={(e) => handleSelectCustomer(e.target.value)}
            className="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all cursor-pointer shadow-2xs"
          >
            {displayedCustomers.map((c) => {
              const isAssigned = selectedStaffId && c.assignedStaffId === selectedStaffId;
              const act = customerActivity[c.id];
              return (
                <option key={c.id} value={c.id}>
                  {act?.hasPendingDraft ? '🔴 [Chờ trả lời] ' : ''}
                  {isAssigned ? '★ ' : ''}
                  {c.name} ({c.id})
                </option>
              );
            })}
          </select>

          {/* Sorted Customer List (Newest questions at top for 1-click switching) */}
          <div className="mt-2 max-h-36 overflow-y-auto overscroll-contain space-y-1 pr-0.5">
            {displayedCustomers.map((c, idx) => {
              const isSelected = c.id === selectedCustomerId;
              const act = customerActivity[c.id];
              const isAssigned = selectedStaffId && c.assignedStaffId === selectedStaffId;
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => handleSelectCustomer(c.id)}
                  className={`w-full text-left px-2.5 py-1.5 rounded-xl border text-[11px] transition-all cursor-pointer flex items-center justify-between gap-1.5 ${
                    isSelected
                      ? 'bg-blue-600 text-white border-blue-600 shadow-xs'
                      : act?.hasPendingDraft
                        ? 'bg-amber-50/90 hover:bg-amber-100/80 text-slate-800 border-amber-300'
                        : 'bg-white hover:bg-slate-100 text-slate-700 border-slate-200/80'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1 font-bold truncate">
                      {idx === 0 && act?.updatedAt && (
                        <span
                          className={`text-[9px] px-1 py-0.2 rounded font-extrabold ${
                            isSelected ? 'bg-white/20 text-white' : 'bg-blue-100 text-blue-700'
                          }`}
                        >
                          MỚI NHẤT
                        </span>
                      )}
                      {isAssigned && <span title="Khách do bạn phụ trách">★</span>}
                      <span className="truncate">{c.name}</span>
                    </div>
                    {act?.lastTitle && (
                      <p
                        className={`text-[10px] truncate mt-0.5 ${
                          isSelected ? 'text-blue-100' : 'text-slate-500'
                        }`}
                      >
                        💬 {act.lastTitle}
                      </p>
                    )}
                  </div>
                  {act?.hasPendingDraft && (
                    <span
                      className={`shrink-0 px-1.5 py-0.5 rounded-full text-[9px] font-bold ${
                        isSelected
                          ? 'bg-amber-300 text-slate-900'
                          : 'bg-amber-500 text-white animate-pulse'
                      }`}
                    >
                      Chờ duyệt
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Quick info card + Orders toggle */}
          <div className="mt-2.5 p-2.5 bg-white rounded-xl border border-slate-200/80 text-[11px] space-y-1.5">
            <div className="flex items-center justify-between text-slate-600">
              <span className="flex items-center gap-1">
                <Phone className="w-3 h-3 text-slate-400" />
                <span>{currentCustomer.phone || 'Chưa cập nhật'}</span>
              </span>
              {selectedStaffId && currentCustomer.assignedStaffId === selectedStaffId && (
                <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                  Phụ trách
                </span>
              )}
            </div>

            {(latestCustomerOrder || currentCustomer.orderId) && (
              <div className="flex items-center justify-between text-slate-600 pt-1 border-t border-blue-100/60">
                <span className="flex items-center gap-1">
                  <Package className="w-3 h-3 text-blue-500" />
                  <b>#{latestCustomerOrder?.order_id || currentCustomer.orderId}</b>
                </span>
                <span className="text-[10px] font-medium text-emerald-700 bg-emerald-100/80 px-1.5 py-0.5 rounded truncate max-w-[130px]">
                  {latestCustomerOrder?.order_status || currentCustomer.orderStatus}
                </span>
              </div>
            )}

            <button
              type="button"
              onClick={() => setShowOrdersDrawer((v) => !v)}
              className="w-full mt-1 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[11px] font-semibold text-blue-600 hover:text-blue-700 cursor-pointer"
            >
              <span>📦 Đơn hàng & Giao dịch ({customerOrders.length})</span>
              {showOrdersDrawer ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>

            {showOrdersDrawer && (
              <div className="pt-1.5 space-y-1.5 max-h-40 overflow-y-auto">
                {customerOrders.length === 0 ? (
                  <p className="text-[10px] text-slate-400 italic">Khách hàng chưa có đơn hàng nào.</p>
                ) : (
                  customerOrders.map((ord) => (
                    <div key={ord.order_id} className="p-2 rounded-lg bg-slate-50 border border-slate-200/70 text-[10px] space-y-0.5">
                      <div className="flex items-center justify-between font-bold text-slate-800">
                        <span>#{ord.order_id}</span>
                        <span className="text-blue-600">{ord.total_amount?.toLocaleString('vi-VN')}đ</span>
                      </div>
                      <p className="text-slate-600 truncate">
                        {ord.product_name || ord.items?.map((i) => i.name).join(', ')}
                      </p>
                      <span className="inline-block text-[9px] font-semibold px-1.5 py-0.2 rounded bg-white border border-slate-200 text-slate-600">
                        {ord.order_status}
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        {/* Sessions Section Header with + New Session */}
        <div className="px-3.5 py-2.5 border-b border-slate-100 flex items-center justify-between">
          <span className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
            <MessageSquare className="w-3.5 h-3.5 text-slate-500" />
            <span>Lịch sử phiên chat</span>
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
        <div className="flex-1 overflow-y-auto overscroll-contain p-2 space-y-1.5">
          {currentSessions.map((s) => {
            const isActive = s.sessionId === activeSessionId;
            const lastMsg = s.messages[s.messages.length - 1];
            const isEditing = editingSessionId === s.sessionId;
            const hasDraftWaiting = Boolean(s.editedDraft && s.editedDraft.trim());

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
                      {hasDraftWaiting && (
                        <span className="px-1.5 py-0.2 rounded-full bg-amber-100 text-amber-800 text-[9px] font-bold border border-amber-300">
                          Chờ duyệt
                        </span>
                      )}
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
                    {s.messageCount ?? s.messages.length} tin
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
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold">
                  Đồng bộ trực tuyến /customer
                </span>
              </div>
              <span className="text-[11px] text-slate-500">{activeSession?.title}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => syncSessionFromSqlite(true)}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-xs font-semibold text-slate-600 cursor-pointer transition-colors"
              title="Đồng bộ tin nhắn mới nhất từ Khách hàng (/customer)"
            >
              <RefreshCw className={`w-3 h-3 ${isSyncing ? 'animate-spin text-blue-600' : ''}`} />
              <span>Đồng bộ</span>
            </button>
          </div>
        </div>

        {/* Message Stream (Customer on LEFT in WHITE, Staff on RIGHT in BLUE, Messenger-style Quoted Question) */}
        <div className="flex-1 overflow-y-auto overscroll-contain p-4 space-y-4 bg-slate-50/40">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 p-8">
              <MessageSquare className="w-12 h-12 mb-3 text-slate-300 stroke-[1.5]" />
              <p className="text-sm font-semibold text-slate-600">Bắt đầu hoặc chờ tin nhắn từ Khách hàng</p>
              <p className="text-xs mt-1 text-slate-400 max-w-xs">
                Đang kết nối phiên chat của khách hàng <b>{currentCustomer.name} ({currentCustomer.id})</b>. Khi khách gửi tin bên <b>/customer</b>, tin nhắn và bản nháp Copilot sẽ tự động hiển thị tại đây.
              </p>
            </div>
          ) : (
            messages.map((m, idx) => {
              const isAck = Boolean(m.isAcknowledgement || m.role === 'acknowledgement');
              const isAgentSide = m.role === 'agent' || m.role === 'acknowledgement';
              const isBlueStaffBubble = isAgentSide && !isAck;
              const repliedQuestion = isAgentSide ? findRepliedCustomerQuestion(messages, idx) : null;

              return (
                <div
                  key={m.id}
                  className={`flex gap-3 ${isAgentSide ? 'justify-end' : 'justify-start'}`}
                >
                  {/* Customer Avatar on the LEFT */}
                  {m.role === 'customer' && (
                    <div className="w-8 h-8 rounded-full bg-white border border-slate-200 text-slate-700 flex items-center justify-center flex-shrink-0 text-sm shadow-2xs">
                      <User className="w-4 h-4" />
                    </div>
                  )}

                  <div className={`max-w-[82%] flex flex-col ${isAgentSide ? 'items-end' : 'items-start'}`}>
                    {/* Messenger-style Faded Quoted Customer Question above Staff/Agent reply */}
                    {isAgentSide && repliedQuestion && (
                      <div
                        className="mb-1 px-3 py-1.5 rounded-xl bg-slate-200/65 border border-slate-300/60 text-[11px] text-slate-600 max-w-full opacity-85 flex items-start gap-1.5 shadow-2xs"
                        title={`Đang trả lời câu hỏi của ${currentCustomer.name}: "${repliedQuestion.content}"`}
                      >
                        <CornerUpLeft className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                        <div className="truncate">
                          <span className="font-semibold text-slate-700 mr-1">
                            Trả lời {currentCustomer.name}:
                          </span>
                          <span className="italic text-slate-600">"{repliedQuestion.content}"</span>
                        </div>
                      </div>
                    )}

                    <div
                      className={`w-full rounded-2xl p-3.5 text-xs whitespace-pre-wrap leading-relaxed ${
                        m.role === 'customer'
                          ? 'bg-white text-slate-800 border border-slate-200 rounded-tl-sm shadow-xs'
                          : isAck
                            ? 'bg-amber-50/95 text-amber-950 border border-amber-200 rounded-tr-sm shadow-2xs'
                            : 'bg-blue-600 text-white rounded-tr-sm shadow-sm'
                      }`}
                    >
                      {m.role === 'customer' && (
                        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 mb-1.5 pb-1 border-b border-slate-100">
                          <span>👤 Khách hàng ({currentCustomer.name})</span>
                        </div>
                      )}
                      {isAck && (
                        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-700 mb-1.5 pb-1 border-b border-amber-200/50">
                          <span>⚡ Phản hồi đệm tức thì (Copilot)</span>
                        </div>
                      )}
                      {!isAck && isAgentSide && (
                        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-blue-100 mb-1.5 pb-1 border-b border-blue-500/60">
                          <span>👨‍💼 Nhân viên CSKH ({selectedStaffName || 'Đã duyệt'})</span>
                        </div>
                      )}

                      {/* Clickable and colored policy badges inside message content */}
                      <div className="leading-relaxed whitespace-pre-wrap">
                        {renderTextWithPolicyLinks(m.content, m.citations, isBlueStaffBubble)}
                      </div>

                      {(() => {
                        const citedMatches = m.content.match(/POL-[A-Z0-9_-]+/gi) || [];
                        const citedSet = new Set(citedMatches.map((c) => c.toUpperCase()));
                        const activeCitations =
                          m.citations && m.citations.length > 0
                            ? m.citations.filter((c) => citedSet.has(c.doc_id.toUpperCase()))
                            : Array.from(citedSet).map((code) => {
                                const found = allPolicies.find((p) => p.doc_id.toUpperCase() === code);
                                return (
                                  found || {
                                    doc_id: code,
                                    title: `Chính sách ${code}`,
                                    content: '',
                                    is_active: true,
                                  }
                                );
                              });

                        if (activeCitations.length === 0) return null;

                        return (
                          <div
                            className={`mt-2.5 pt-2 border-t text-[11px] ${
                              isBlueStaffBubble
                                ? 'border-blue-500/60 text-blue-100'
                                : 'border-slate-200/60 text-slate-500'
                            }`}
                          >
                            <span className="font-semibold block mb-1">
                              📚 File chính sách đính kèm (Bấm để xem):
                            </span>
                            <div className="flex flex-wrap gap-1.5">
                              {activeCitations.map((c) => (
                                <button
                                  key={c.doc_id}
                                  type="button"
                                  onClick={() => handleOpenPolicyDoc(c.doc_id, m.citations)}
                                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold cursor-pointer transition-colors ${
                                    isBlueStaffBubble
                                      ? 'bg-white text-blue-700 hover:bg-blue-50 border border-blue-200 shadow-2xs'
                                      : 'bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100'
                                  }`}
                                >
                                  <FileText className="w-3 h-3 text-blue-600" />
                                  <span>
                                    [{c.doc_id}] {c.title}
                                  </span>
                                </button>
                              ))}
                            </div>
                          </div>
                        );
                      })()}

                      <span
                        className={`block text-[10px] mt-1.5 text-right ${
                          m.role === 'customer'
                            ? 'text-slate-400'
                            : isAck
                              ? 'text-amber-600/70'
                              : 'text-blue-200'
                        }`}
                      >
                        {m.timestamp}
                      </span>
                    </div>
                  </div>

                  {/* Staff / Agent Avatar on the RIGHT */}
                  {isAgentSide && (
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm shadow-2xs ${
                        isAck ? 'bg-amber-100 text-amber-600' : 'bg-blue-600 text-white'
                      }`}
                    >
                      {isAck ? <Bot className="w-4 h-4" /> : <CheckCircle className="w-4 h-4" />}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* E-commerce Multi-message Banner & Trigger Button */}
        {hasUnrespondedCustomerMsg && !isLoading && !hasPendingCopilot && (
          <div className="px-4 py-2 bg-blue-50/90 border-t border-blue-100 flex items-center justify-between">
            <span className="text-[11px] text-blue-700">
              Khách đang chờ phản hồi. Bấm để yêu cầu AI Copilot phân tích & soạn bản nháp trả lời:
            </span>
            <button
              onClick={handleManualRequestResponse}
              className="flex items-center gap-1.5 px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold transition-all shadow-xs cursor-pointer animate-pulse"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>⚡ Yêu cầu Copilot soạn nháp</span>
            </button>
          </div>
        )}

        {/* Input Bar with Mode Switcher (Direct Staff Reply vs Customer Simulation) */}
        <div className="p-3 border-t border-slate-100 bg-white space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500 px-1">
            <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg">
              <button
                type="button"
                onClick={() => setChatInputMode('simulate_customer')}
                className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                  chatInputMode === 'simulate_customer'
                    ? 'bg-white text-blue-700 shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                🧪 Giả lập Khách hỏi (Test Copilot)
              </button>
              <button
                type="button"
                onClick={() => setChatInputMode('staff_reply')}
                className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                  chatInputMode === 'staff_reply'
                    ? 'bg-white text-emerald-700 shadow-2xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                👤 Nhân viên nhắn trực tiếp
              </button>
            </div>

            {chatInputMode === 'simulate_customer' && (
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoTriggerCopilot}
                  onChange={(e) => setAutoTriggerCopilot(e.target.checked)}
                  className="rounded text-blue-600 focus:ring-blue-500 cursor-pointer"
                />
                <span className="font-medium text-slate-600">Tự động gọi Copilot</span>
              </label>
            )}
          </div>

          <form onSubmit={handleSend} className="flex gap-2">
            <input
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              placeholder={
                chatInputMode === 'staff_reply'
                  ? `Nhập phản hồi trực tiếp của Nhân viên gửi tới ${currentCustomer.name}...`
                  : autoTriggerCopilot
                    ? `Nhập câu hỏi từ khách hàng ${currentCustomer.name} để Copilot phân tích...`
                    : `Nhập dòng tin nhắn của khách hàng (bấm gửi rồi bấm 'Yêu cầu trả lời')...`
              }
              disabled={isLoading || !activeSession}
              className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 disabled:bg-slate-50"
            />
            <button
              type="submit"
              disabled={isLoading || !inputQuery.trim() || !activeSession}
              className={`px-4 py-2.5 text-white rounded-xl text-xs font-semibold transition-colors disabled:opacity-50 flex items-center gap-1.5 cursor-pointer shadow-sm ${
                chatInputMode === 'staff_reply'
                  ? 'bg-emerald-600 hover:bg-emerald-700'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {isLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              <span>
                {chatInputMode === 'staff_reply'
                  ? 'Gửi cho Khách'
                  : autoTriggerCopilot
                    ? 'Gửi & Soạn nháp'
                    : 'Gửi dòng tin'}
              </span>
            </button>
            {chatInputMode === 'simulate_customer' && !autoTriggerCopilot && (
              <button
                type="button"
                onClick={handleManualRequestResponse}
                disabled={isLoading || !activeSession || activeSession.messages.length === 0}
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
        className="flex-shrink-0 flex flex-col space-y-4 overflow-y-auto overscroll-contain"
      >
        {hasPendingCopilot ? (
          <>
            {/* CS Draft Response Editor (Placed at top of Column 3 for immediate action!) */}
            <Card title="✍️ Bản nháp Đề xuất cho Nhân viên">
              {/* Messenger-style Faded Quoted Customer Question being answered by this draft */}
              {(() => {
                const latestCustMsg = [...messages].reverse().find((m) => m.role === 'customer');
                if (!latestCustMsg) return null;
                return (
                  <div className="mb-2.5 px-3 py-2 rounded-xl bg-slate-100/90 border border-slate-200/90 text-[11px] text-slate-600 flex items-start gap-1.5 opacity-90">
                    <CornerUpLeft className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <span className="font-semibold text-slate-700 block">
                        Đang trả lời câu hỏi của {currentCustomer.name}:
                      </span>
                      <p className="italic text-slate-600 line-clamp-2 mt-0.5">"{latestCustMsg.content}"</p>
                    </div>
                  </div>
                );
              })()}

              {copilotResponse?.customer_acknowledgement && (
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
                <div className="mb-2.5 p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs leading-relaxed max-h-56 overflow-y-auto whitespace-pre-wrap text-slate-800 font-sans shadow-inner">
                  {renderTextWithPolicyLinks(editedDraft, copilotResponse?.citations)}
                </div>
              ) : (
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

            {/* Guardrail & Classification Analysis Card */}
            {copilotResponse && (
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
            )}

            {/* Dynamic Order Card (Module 3) */}
            {copilotResponse?.order_data && (
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

            {/* Citations List with "Xem văn bản" button */}
            {copilotResponse?.citations && copilotResponse.citations.length > 0 && (
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
          <div className="flex flex-col items-center justify-center text-center p-8 bg-white rounded-2xl border border-blue-200/80 shadow-xs">
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
          <div className="flex flex-col items-center justify-center text-center p-6 bg-white rounded-2xl border border-slate-200 text-slate-400">
            <Bot className="w-10 h-10 mb-2 text-blue-500 stroke-[1.5]" />
            <p className="text-sm font-semibold text-slate-700">Khung làm việc AI Copilot</p>
            <p className="text-xs mt-1 text-slate-500 max-w-xs">
              Khi khách hàng gửi câu hỏi (từ trang <b>/customer</b> hoặc tại đây), AI Copilot sẽ tự động phân tích ý định, kiểm tra chốt chặn an toàn và soạn sẵn bản nháp tại đây để nhân viên duyệt gửi.
            </p>
            {hasUnrespondedCustomerMsg && (
              <button
                type="button"
                onClick={handleManualRequestResponse}
                className="mt-3 flex items-center gap-1.5 px-3.5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition-all shadow-sm cursor-pointer"
              >
                <Zap className="w-3.5 h-3.5" />
                <span>⚡ Kích hoạt Copilot cho tin nhắn gần nhất</span>
              </button>
            )}
          </div>
        )}

        {/* Always show Customer Orders & Transactions Card in Column 3 for quick reference */}
        <Card title={`📦 Đơn hàng & Giao dịch của ${currentCustomer.name} (${customerOrders.length})`}>
          {customerOrders.length === 0 ? (
            <p className="text-xs text-slate-400 italic">Khách hàng chưa có đơn hàng nào trên hệ thống.</p>
          ) : (
            <div className="space-y-2 text-xs max-h-64 overflow-y-auto pr-1">
              {customerOrders.map((ord) => (
                <div
                  key={ord.order_id}
                  className="p-2.5 bg-slate-50 rounded-xl border border-slate-200/80 space-y-1"
                >
                  <div className="flex items-center justify-between font-bold text-slate-800">
                    <span className="text-blue-700">#{ord.order_id}</span>
                    <Badge variant="info">{ord.order_status}</Badge>
                  </div>
                  <p className="text-slate-700 font-medium">
                    {ord.product_name || ord.items?.map((i) => i.name).join(', ')}
                  </p>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-200/60">
                    <span className="font-semibold text-slate-800">
                      {ord.total_amount?.toLocaleString('vi-VN')} VND
                    </span>
                    <span>{ord.carrier || 'TikiNow'} • {ord.estimated_delivery || ord.created_at || ''}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
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
                type="button"
                onClick={() => setViewingPolicy(null)}
                className="w-8 h-8 rounded-full bg-slate-100 hover:bg-red-100 text-slate-500 hover:text-red-600 flex items-center justify-center transition-colors cursor-pointer"
                title="Đóng cửa sổ xem chính sách (X)"
              >
                <X className="w-4 h-4" />
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
