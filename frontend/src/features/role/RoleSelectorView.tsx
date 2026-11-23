import React from 'react';
import { Bot, User, ShieldCheck, ArrowRight, MessageSquare, FileText, Sparkles } from 'lucide-react';

interface RoleSelectorViewProps {
  onSelectRole: (role: 'customer' | 'staff') => void;
}

export const RoleSelectorView: React.FC<RoleSelectorViewProps> = ({ onSelectRole }) => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50/40 to-indigo-50 flex flex-col items-center justify-center p-4 sm:p-8">
      <div className="w-full max-w-4xl">
        {/* Hero Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/25 mb-4">
            <Bot className="w-8 h-8" />
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
            E-Commerce Support Copilot
          </h1>
          <p className="mt-2 text-sm sm:text-base text-slate-600 max-w-xl mx-auto">
            Chọn vai trò truy cập để trải nghiệm cổng hỗ trợ khách hàng hoặc không gian làm việc dành cho nhân viên CSKH.
          </p>
        </div>

        {/* 2 Role Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Customer Card */}
          <button
            type="button"
            onClick={() => onSelectRole('customer')}
            className="group text-left bg-white rounded-2xl border border-slate-200 p-7 shadow-sm hover:shadow-xl hover:border-blue-400 transition-all duration-200 flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-5">
                <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center group-hover:bg-blue-600 group-hover:text-white transition-colors">
                  <User className="w-6 h-6" />
                </div>
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-100">
                  Route: /customer
                </span>
              </div>
              <h2 className="text-xl font-bold text-slate-900 mb-2">Tôi là Khách hàng</h2>
              <p className="text-sm text-slate-600 leading-relaxed mb-5">
                Tra cứu trạng thái đơn hàng, đổi trả, khuyến mãi và trò chuyện trực tiếp với trợ lý AI theo từng tài khoản khách hàng.
              </p>
              <ul className="space-y-2 text-xs text-slate-500 mb-6">
                <li className="flex items-center gap-2">
                  <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
                  Quản lý nhiều phiên chat theo từng tài khoản
                </li>
                <li className="flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5 text-blue-500" />
                  Tùy chỉnh hiển thị & thông tin cá nhân trong Cài đặt
                </li>
              </ul>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-100 text-sm font-semibold text-blue-600 group-hover:text-blue-700">
              <span>Vào Cổng Khách hàng</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </div>
          </button>

          {/* Staff Card */}
          <button
            type="button"
            onClick={() => onSelectRole('staff')}
            className="group text-left bg-white rounded-2xl border border-slate-200 p-7 shadow-sm hover:shadow-xl hover:border-indigo-400 transition-all duration-200 flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-5">
                <div className="w-12 h-12 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100">
                  Route: /staff
                </span>
              </div>
              <h2 className="text-xl font-bold text-slate-900 mb-2">Tôi là Nhân viên</h2>
              <p className="text-sm text-slate-600 leading-relaxed mb-5">
                Truy cập Copilot Workbench hỗ trợ khách hàng, kiểm duyệt bản nháp, quản lý chính sách RAG và theo dõi Telemetry.
              </p>
              <ul className="space-y-2 text-xs text-slate-500 mb-6">
                <li className="flex items-center gap-2">
                  <ShieldCheck className="w-3.5 h-3.5 text-indigo-500" />
                  Kiểm duyệt phản hồi Copilot & tra cứu đơn hàng
                </li>
                <li className="flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5 text-indigo-500" />
                  Quản lý Chính sách, Audit Log & Kiểm định hệ thống
                </li>
              </ul>
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-100 text-sm font-semibold text-indigo-600 group-hover:text-indigo-700">
              <span>Vào Không gian Nhân viên</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </div>
          </button>
        </div>
      </div>
    </div>
  );
};
