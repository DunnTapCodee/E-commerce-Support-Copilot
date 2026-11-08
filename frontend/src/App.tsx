import React, { useState } from 'react';
import { MessageSquare, FileText, Bell, BarChart3, Bot, ShoppingBag, FlaskConical } from 'lucide-react';
import { ChatView } from './features/chat/ChatView';
import { PolicyListView } from './features/policies/PolicyListView';
import { AuditNotificationView } from './features/notifications/AuditNotificationView';
import { TelemetryDashboardView } from './features/telemetry/TelemetryDashboardView';
import { EvaluationDashboardView } from './features/evaluation/EvaluationDashboardView';

type TabType = 'chat' | 'policies' | 'notifications' | 'telemetry' | 'evaluation';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('chat');

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Top Navbar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
        <div className="w-full max-w-[1920px] mx-auto px-3 sm:px-5 lg:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900 leading-tight">
                E-Commerce Support Copilot
              </h1>
              <p className="text-[11px] text-slate-500">Hệ thống Trợ lý CSKH & Tri thức Thông minh </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex space-x-1 bg-slate-100 p-1 rounded-xl">
            <button
              onClick={() => setActiveTab('chat')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${activeTab === 'chat'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
                }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Hội thoại Copilot</span>
            </button>

            <button
              onClick={() => setActiveTab('policies')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${activeTab === 'policies'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
                }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Quản lý Chính sách</span>
            </button>

            <button
              onClick={() => setActiveTab('notifications')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${activeTab === 'notifications'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
                }`}
            >
              <Bell className="w-3.5 h-3.5" />
              <span>Thông báo Biến động</span>
            </button>

            <button
              onClick={() => setActiveTab('telemetry')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${activeTab === 'telemetry'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
                }`}
            >
              <BarChart3 className="w-3.5 h-3.5" />
              <span>Telemetry</span>
            </button>

            <button
              onClick={() => setActiveTab('evaluation')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${activeTab === 'evaluation'
                ? 'bg-white text-blue-600 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
                }`}
            >
              <FlaskConical className="w-3.5 h-3.5" />
              <span>Kiểm định Hệ thống</span>
            </button>
          </nav>
        </div>
      </header>

      {/* Main View Area - Kept mounted in DOM so tab switching preserves full conversation state */}
      <main className="flex-1 w-full max-w-[1920px] mx-auto px-2 sm:px-4 py-2 sm:py-3">
        <div className={activeTab === 'chat' ? 'block' : 'hidden'}>
          <ChatView />
        </div>
        <div className={activeTab === 'policies' ? 'block' : 'hidden'}>
          <PolicyListView />
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

