import React, { useState } from 'react';
import { MessageSquare, FileText, Bell, BarChart3, Bot, ShoppingBag } from 'lucide-react';
import { ChatView } from './features/chat/ChatView';
import { PolicyListView } from './features/policies/PolicyListView';
import { AuditNotificationView } from './features/notifications/AuditNotificationView';
import { TelemetryDashboardView } from './features/telemetry/TelemetryDashboardView';

type TabType = 'chat' | 'policies' | 'notifications' | 'telemetry';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('chat');

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Top Navbar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
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
          </nav>
        </div>
      </header>

      {/* Main View Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {activeTab === 'chat' && <ChatView />}
        {activeTab === 'policies' && <PolicyListView />}
        {activeTab === 'notifications' && <AuditNotificationView />}
        {activeTab === 'telemetry' && <TelemetryDashboardView />}
      </main>
    </div>
  );
};

