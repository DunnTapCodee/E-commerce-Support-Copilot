import React, { useEffect, useState } from 'react';
import {
  MessageSquare,
  FileText,
  Bell,
  BarChart3,
  Bot,
  FlaskConical,
  ArrowLeftRight,
  Users,
  ShieldCheck,
} from 'lucide-react';
import { ChatView } from './features/chat/ChatView';
import { PolicyListView } from './features/policies/PolicyListView';
import { AuditNotificationView } from './features/notifications/AuditNotificationView';
import { TelemetryDashboardView } from './features/telemetry/TelemetryDashboardView';
import { EvaluationDashboardView } from './features/evaluation/EvaluationDashboardView';
import { RoleSelectorView } from './features/role/RoleSelectorView';
import { CustomerPortalView } from './features/customer/CustomerPortalView';
import { StaffCustomerManagerView } from './features/staff/StaffCustomerManagerView';
import { apiClient } from './lib/api-client';
import { StaffProfile } from './types';

type RoutePath = '/' | '/customer' | '/staff';
type TabType = 'customers' | 'policies' | 'chat' | 'notifications' | 'telemetry' | 'evaluation';

const FALLBACK_STAFF: StaffProfile[] = [
  {
    staff_id: 'staff-01',
    name: 'Nguyễn Minh Anh',
    email: 'minhanh@tiki-copilot.vn',
    role: 'Senior CS',
    department: 'Chăm sóc Đơn hàng & Vận chuyển',
  },
  {
    staff_id: 'staff-02',
    name: 'Trần Hoàng Nam',
    email: 'hoangnam@tiki-copilot.vn',
    role: 'Policy Admin',
    department: 'Quản lý Chính sách & Khiếu nại',
  },
  {
    staff_id: 'staff-03',
    name: 'Lê Thảo Vy',
    email: 'thaovy@tiki-copilot.vn',
    role: 'CS Agent',
    department: 'Hỗ trợ Thanh toán & Hoàn tiền',
  },
];

function normalizeRoute(pathname: string): RoutePath {
  if (pathname.startsWith('/customer')) return '/customer';
  if (pathname.startsWith('/staff')) return '/staff';
  return '/';
}

export const App: React.FC = () => {
  const [route, setRoute] = useState<RoutePath>(() => normalizeRoute(window.location.pathname));
  // Default to 'chat' (Hỗ trợ & Copilot) so Staff's core support workbench is front-and-center on /staff
  const [activeTab, setActiveTab] = useState<TabType>('chat');

  const [staffList, setStaffList] = useState<StaffProfile[]>(FALLBACK_STAFF);
  const [selectedStaffId, setSelectedStaffId] = useState<string>('staff-01');
  const [copilotTarget, setCopilotTarget] = useState<{ customerId?: string; sessionId?: string }>({});

  useEffect(() => {
    const handlePopState = () => {
      setRoute(normalizeRoute(window.location.pathname));
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    let mounted = true;
    const loadStaff = async () => {
      const list = await apiClient.listStaff();
      if (mounted && list.length > 0) {
        setStaffList(list);
        setSelectedStaffId((prev) => (list.some((s) => s.staff_id === prev) ? prev : list[0].staff_id));
      }
    };
    loadStaff();
    return () => {
      mounted = false;
    };
  }, []);

  const navigateTo = (target: RoutePath) => {
    if (window.location.pathname !== target) {
      window.history.pushState({}, '', target);
    }
    setRoute(target);
  };

  const currentStaff = staffList.find((s) => s.staff_id === selectedStaffId) || staffList[0];

  // Route 1: Landing / Role Switcher (/)
  if (route === '/') {
    return (
      <RoleSelectorView
        onSelectRole={(role) => navigateTo(role === 'customer' ? '/customer' : '/staff')}
      />
    );
  }

  // Route 2: Customer Portal (/customer)
  if (route === '/customer') {
    return <CustomerPortalView onSwitchRole={() => navigateTo('/')} />;
  }

  // Route 3: Staff Workspace (/staff)
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Top Navbar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
        <div className="w-full max-w-[1920px] mx-auto px-3 sm:px-5 lg:px-6 h-16 flex items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center shadow-md shadow-indigo-500/20">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-slate-900 leading-tight">
                  Cổng Quản trị Nhân viên (Staff)
                </h1>
                <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                  {currentStaff?.role || 'Staff'}
                </span>
              </div>
              <p className="text-[11px] text-slate-500">{currentStaff?.department || 'Hệ thống CSKH & Tri thức'}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            {/* Staff Selector Dropdown */}
            <div className="flex items-center gap-2 bg-indigo-50/70 border border-indigo-200 rounded-xl px-3 py-1.5">
              <ShieldCheck className="w-4 h-4 text-indigo-600 shrink-0" />
              <label htmlFor="staff-selector" className="text-xs font-medium text-slate-600 hidden md:inline">
                Nhân viên:
              </label>
              <select
                id="staff-selector"
                value={selectedStaffId}
                onChange={(e) => setSelectedStaffId(e.target.value)}
                className="bg-transparent text-xs font-bold text-indigo-900 focus:outline-none cursor-pointer"
              >
                {staffList.map((st) => (
                  <option key={st.staff_id} value={st.staff_id}>
                    {st.name} ({st.staff_id})
                  </option>
                ))}
              </select>
            </div>

            {/* Navigation Tabs (Copilot Support first!) */}
            <nav className="flex space-x-1 bg-slate-100 p-1 rounded-xl overflow-x-auto">
              <button
                onClick={() => setActiveTab('chat')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap cursor-pointer ${
                  activeTab === 'chat'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5" />
                <span>Hỗ trợ & Copilot</span>
              </button>

              <button
                onClick={() => setActiveTab('customers')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap cursor-pointer ${
                  activeTab === 'customers'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Users className="w-3.5 h-3.5" />
                <span>Quản lý Khách hàng</span>
              </button>

              <button
                onClick={() => setActiveTab('policies')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap cursor-pointer ${
                  activeTab === 'policies'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                <span>Quản lý Chính sách (Bot Knowledge)</span>
              </button>

              <button
                onClick={() => setActiveTab('notifications')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
                  activeTab === 'notifications'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Bell className="w-3.5 h-3.5" />
                <span className="hidden 2xl:inline">Biến động</span>
              </button>

              <button
                onClick={() => setActiveTab('telemetry')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
                  activeTab === 'telemetry'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <BarChart3 className="w-3.5 h-3.5" />
                <span className="hidden 2xl:inline">Telemetry</span>
              </button>

              <button
                onClick={() => setActiveTab('evaluation')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
                  activeTab === 'evaluation'
                    ? 'bg-white text-indigo-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <FlaskConical className="w-3.5 h-3.5" />
                <span className="hidden 2xl:inline">Kiểm định</span>
              </button>
            </nav>

            {/* Switch Role Button */}
            <button
              type="button"
              onClick={() => navigateTo('/')}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 hover:text-slate-900 transition-colors shadow-sm shrink-0"
              title="Quay lại màn hình chọn vai trò"
            >
              <ArrowLeftRight className="w-3.5 h-3.5 text-indigo-600" />
              <span className="hidden xl:inline">Đổi vai trò</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main View Area */}
      <main className="flex-1 w-full max-w-[1920px] mx-auto px-2 sm:px-4 py-2 sm:py-3">
        <div className={activeTab === 'chat' ? 'block' : 'hidden'}>
          <ChatView
            selectedStaffId={selectedStaffId}
            selectedStaffName={currentStaff?.name || selectedStaffId}
            initialCustomerId={copilotTarget.customerId}
            initialSessionId={copilotTarget.sessionId}
          />
        </div>
        <div className={activeTab === 'customers' ? 'block' : 'hidden'}>
          <StaffCustomerManagerView
            selectedStaffId={selectedStaffId}
            selectedStaffName={currentStaff?.name || selectedStaffId}
            onOpenInCopilot={(custId, sessId) => {
              setCopilotTarget({ customerId: custId, sessionId: sessId });
              setActiveTab('chat');
            }}
          />
        </div>
        <div className={activeTab === 'policies' ? 'block' : 'hidden'}>
          <PolicyListView currentStaffId={selectedStaffId} />
        </div>
        <div className={activeTab === 'notifications' ? 'block' : 'hidden'}>
          <AuditNotificationView />
        </div>
        <div className={activeTab === 'telemetry' ? 'block' : 'hidden'}>
          <TelemetryDashboardView />
        </div>
        <div className={activeTab === 'evaluation' ? 'block' : 'hidden'}>
          {activeTab === 'evaluation' && <EvaluationDashboardView />}
        </div>
      </main>
    </div>
  );
};
