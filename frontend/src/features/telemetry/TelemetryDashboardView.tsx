import React, { useState, useEffect } from 'react';
import { Activity, ShieldCheck, Zap, RefreshCw, AlertTriangle, CheckCircle, Clock, Eye } from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { formatSystemTimeWithSeconds } from '../../lib/time';

export const TelemetryDashboardView: React.FC = () => {
  const [stats, setStats] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<any | null>(null);

  const fetchStats = async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.getStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to fetch telemetry stats:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const timer = setInterval(() => {
      fetchStats();
    }, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-slate-800">Thống kê Hiệu năng & An toàn Hệ thống (Telemetry)</h2>
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              Auto-sync (3s)
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Theo dõi tổng lượt truy vấn, độ trễ thời gian thực và phân bổ các chốt chặn an toàn Guardrails.
          </p>
        </div>
        <button
          onClick={fetchStats}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-xl text-xs font-semibold transition-colors shadow-2xs cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Làm mới</span>
        </button>
      </div>

      {stats ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <Card className="!p-4">
              <span className="text-xs text-slate-500">Tổng số truy vấn</span>
              <p className="text-2xl font-bold text-slate-800 mt-1">{stats.total_interactions || stats.total_queries || 0}</p>
            </Card>
            <Card className="!p-4">
              <span className="text-xs text-slate-500">Tỷ lệ duyệt thủ công</span>
              <p className="text-2xl font-bold text-emerald-600 mt-1">
                {Math.round((stats.auto_approved_rate || 0) * 100)}%
              </p>
            </Card>
            <Card className="!p-4">
              <span className="text-xs text-slate-500">Tỷ lệ can thiệp Guardrail</span>
              <p className="text-2xl font-bold text-amber-600 mt-1">
                {Math.round(stats.safety_block_rate || (stats.escalation_rate || 0) * 100)}%
              </p>
            </Card>
            <Card className="!p-4">
              <span className="text-xs text-slate-500">Độ trễ trung bình</span>
              <p className="text-2xl font-bold text-blue-600 mt-1">{Math.round(stats.average_latency_ms || stats.avg_latency_ms || 0)} ms</p>
            </Card>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <Card title="🎯 Phân bổ Ý định Phân loại">
              <div className="space-y-2 text-xs">
                {Object.entries(stats.intent_distribution || {}).map(([intent, count]) => (
                  <div key={intent} className="flex justify-between items-center p-2 rounded-lg bg-slate-50">
                    <span className="font-semibold text-slate-700">{intent}</span>
                    <span className="font-mono text-slate-500">{String(count)} lượt</span>
                  </div>
                ))}
                {(!stats.intent_distribution || Object.keys(stats.intent_distribution).length === 0) && (
                  <p className="text-slate-400 text-xs italic">Chưa có dữ liệu ý định</p>
                )}
              </div>
            </Card>

            <Card title="🛡️ Tác vụ Chốt chặn Guardrails">
              <div className="space-y-2 text-xs">
                {Object.entries(stats.guardrail_breakdown || stats.guardrail_actions || {}).map(([action, count]) => (
                  <div key={action} className="flex justify-between items-center p-2 rounded-lg bg-slate-50">
                    <span className="font-semibold text-slate-700">{action}</span>
                    <span className="font-mono text-slate-500">{String(count)} lần</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* Recent Records Table */}
          <Card title="📋 Lịch sử Truy vấn & Giám sát Chốt chặn Thời gian thực">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-slate-400 font-medium">
                    <th className="py-2.5 px-3">Thời gian</th>
                    <th className="py-2.5 px-3">Câu hỏi khách hàng</th>
                    <th className="py-2.5 px-3">Ý định</th>
                    <th className="py-2.5 px-3">Chốt chặn Guardrail</th>
                    <th className="py-2.5 px-3">Duyệt CSKH</th>
                    <th className="py-2.5 px-3">Độ trễ</th>
                    <th className="py-2.5 px-3 text-right">Chi tiết</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-600">
                  {(stats.recent_records || []).slice(0, 20).map((r: any, idx: number) => {
                    const isEscalate = r.guardrail_action === 'ESCALATE_HUMAN';
                    const isProceed = r.guardrail_action === 'PROCEED_TO_LLM';
                    const isFinancial = r.guardrail_action === 'DIRECT_REFUND_FORM';
                    return (
                      <tr key={r.interaction_id || idx} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-2.5 px-3 font-mono text-[11px] text-slate-400 whitespace-nowrap">
                          {r.timestamp ? formatSystemTimeWithSeconds(r.timestamp) : 'N/A'}
                        </td>
                        <td className="py-2.5 px-3 max-w-[240px] truncate font-medium text-slate-800" title={r.customer_query}>
                          {r.customer_query}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px] font-mono">
                            {r.predicted_intent || 'N/A'}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <Badge variant={isProceed ? 'success' : isFinancial ? 'warning' : 'danger'}>
                            {r.guardrail_action}
                          </Badge>
                        </td>
                        <td className="py-2.5 px-3">
                          {r.human_action ? (
                            <Badge variant={r.human_action === 'APPROVE' ? 'success' : 'info'}>
                              {r.human_action}
                            </Badge>
                          ) : (
                            <span className="text-slate-400 text-[11px] italic">Chờ duyệt</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500">
                          {r.latency_ms ? `${r.latency_ms}ms` : '-'}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <button
                            onClick={() => setSelectedRecord(r)}
                            className="p-1 hover:bg-slate-100 rounded text-slate-500 hover:text-blue-600 transition-colors cursor-pointer"
                            title="Xem chi tiết bản nháp"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {(!stats.recent_records || stats.recent_records.length === 0) && (
                    <tr>
                      <td colSpan={7} className="py-6 text-center text-slate-400">
                        Chưa có lịch sử tương tác nào được ghi nhận.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      ) : (
        <div className="p-8 text-center text-slate-400 text-xs">
          {isLoading ? 'Đang tải dữ liệu telemetry...' : 'Chưa có dữ liệu thống kê.'}
        </div>
      )}

      {/* Record Details Modal */}
      {selectedRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-4 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-blue-600" />
                <span>Chi tiết Tương tác Telemetry</span>
              </h3>
              <button
                onClick={() => setSelectedRecord(null)}
                className="text-slate-400 hover:text-slate-600 text-sm font-bold p-1 cursor-pointer"
              >
                ✕
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <span className="text-slate-400 block mb-0.5">ID Tương tác:</span>
                <span className="font-mono text-slate-600 text-[11px]">{selectedRecord.interaction_id}</span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Câu hỏi khách hàng:</span>
                <p className="p-2.5 bg-slate-50 rounded-lg text-slate-800 font-medium">{selectedRecord.customer_query}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <span className="text-slate-400 block mb-0.5">Ý định phân loại:</span>
                  <span className="font-mono text-blue-700 font-semibold">{selectedRecord.predicted_intent}</span>
                </div>
                <div>
                  <span className="text-slate-400 block mb-0.5">Tác vụ Guardrail:</span>
                  <Badge variant={selectedRecord.guardrail_action === 'PROCEED_TO_LLM' ? 'success' : 'danger'}>
                    {selectedRecord.guardrail_action}
                  </Badge>
                </div>
              </div>
              {selectedRecord.retrieved_doc_ids && (
                <div>
                  <span className="text-slate-400 block mb-0.5">Căn cứ trích dẫn:</span>
                  <span className="font-mono text-slate-700">{selectedRecord.retrieved_doc_ids}</span>
                </div>
              )}
              <div>
                <span className="text-slate-400 block mb-0.5">Bản nháp sinh ra (Raw Draft):</span>
                <div className="p-2.5 bg-slate-50 rounded-lg text-slate-700 max-h-40 overflow-y-auto whitespace-pre-wrap leading-relaxed text-[11px]">
                  {selectedRecord.raw_draft_text}
                </div>
              </div>
              {selectedRecord.final_sent_text && (
                <div>
                  <span className="text-slate-400 block mb-0.5">Nội dung nhân viên gửi thực tế:</span>
                  <div className="p-2.5 bg-emerald-50 text-emerald-800 rounded-lg max-h-40 overflow-y-auto whitespace-pre-wrap leading-relaxed text-[11px]">
                    {selectedRecord.final_sent_text}
                  </div>
                </div>
              )}
            </div>
            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedRecord(null)}
                className="px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold cursor-pointer"
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
