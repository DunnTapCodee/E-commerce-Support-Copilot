import React, { useState, useEffect } from 'react';
import { Activity, ShieldCheck, Zap, RefreshCw, AlertTriangle, CheckCircle, Clock, Eye, Send } from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { formatSystemTimeWithSeconds } from '../../lib/time';
import { DelayNotificationRecord, IncidentClusterSummary } from '../../types';

export const TelemetryDashboardView: React.FC = () => {
  const [stats, setStats] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<any | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<'overview' | 'operations'>('overview');
  const [clusters, setClusters] = useState<IncidentClusterSummary[]>([]);
  const [delayNotifications, setDelayNotifications] = useState<DelayNotificationRecord[]>([]);
  const [opsMessage, setOpsMessage] = useState<string | null>(null);
  const [isRunningOps, setIsRunningOps] = useState(false);

  const fetchStats = async () => {
    setIsLoading(true);
    try {
      const [data, clusterRes, delayRes] = await Promise.all([
        apiClient.getStats(),
        apiClient.getIncidentClusters(24, 2),
        apiClient.listDelayNotifications(),
      ]);
      setStats(data);
      setClusters(clusterRes?.clusters || []);
      setDelayNotifications(delayRes?.notifications || []);
    } catch (err) {
      console.error('Failed to fetch telemetry stats:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleScanOverdueOrders = async () => {
    setIsRunningOps(true);
    setOpsMessage(null);
    try {
      const res = await apiClient.scanProactiveDelay(undefined, 3);
      setDelayNotifications(res.notifications || []);
      setOpsMessage(
        `✅ Đã quét ngày ${res.reference_date}: phát hiện ${res.total_overdue_matching} đơn Shipping trễ > 3 ngày (tạo mới ${res.newly_created_count} thông báo voucher 30k).`
      );
    } catch (err: any) {
      setOpsMessage(`⚠️ Lỗi quét đơn trễ: ${err?.message || 'Thất bại'}`);
    } finally {
      setIsRunningOps(false);
    }
  };

  const handleDispatchPendingDelay = async () => {
    setIsRunningOps(true);
    setOpsMessage(null);
    try {
      const res = await apiClient.dispatchDelayNotifications(undefined, 'CS Staff');
      const listRes = await apiClient.listDelayNotifications();
      setDelayNotifications(listRes.notifications || []);
      setOpsMessage(`📨 Đã duyệt gửi hàng loạt ${res.dispatched_count} thông báo xin lỗi + voucher 30k.`);
    } catch (err: any) {
      setOpsMessage(`⚠️ Lỗi gửi hàng loạt: ${err?.message || 'Thất bại'}`);
    } finally {
      setIsRunningOps(false);
    }
  };

  const handleBroadcastCluster = async (cluster: IncidentClusterSummary) => {
    setIsRunningOps(true);
    setOpsMessage(null);
    try {
      await apiClient.broadcastIncident({
        cluster_id: cluster.cluster_id,
        issue_topic: cluster.issue_topic,
        message_text: cluster.suggested_broadcast,
        performed_by: 'CS Staff',
      });
      setOpsMessage(`📢 Đã phát hành mẫu thông báo hàng loạt cho cụm '${cluster.issue_topic}' (${cluster.count} phản ánh).`);
    } catch (err: any) {
      setOpsMessage(`⚠️ Lỗi phát thông báo cụm: ${err?.message || 'Thất bại'}`);
    } finally {
      setIsRunningOps(false);
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
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-slate-100 p-0.5 rounded-xl text-xs">
            <button
              type="button"
              onClick={() => setActiveSubTab('overview')}
              className={`px-3 py-1.5 rounded-lg font-semibold cursor-pointer transition-colors ${
                activeSubTab === 'overview' ? 'bg-white text-blue-700 shadow-2xs' : 'text-slate-600'
              }`}
            >
              📊 Hiệu năng & Guardrails
            </button>
            <button
              type="button"
              onClick={() => setActiveSubTab('operations')}
              className={`px-3 py-1.5 rounded-lg font-semibold cursor-pointer transition-colors ${
                activeSubTab === 'operations' ? 'bg-white text-rose-700 shadow-2xs' : 'text-slate-600'
              }`}
            >
              🚨 Sự vụ & Quét Trễ Đơn ({delayNotifications.filter((n) => n.status === 'PENDING_SEND').length})
            </button>
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
      </div>

      {activeSubTab === 'operations' && (
        <div className="space-y-6">
          {opsMessage && (
            <div className="p-3 rounded-xl bg-blue-50 border border-blue-200 text-xs font-medium text-blue-900">
              {opsMessage}
            </div>
          )}

          {/* Proactive Overdue Shipping Delay Agent (> 3 days, 30k voucher) */}
          <Card title="🚚 Tác tử Quét Đơn Giao Trễ > 3 Ngày (Tặng Voucher Tri Ân 30.000đ)">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <p className="text-xs text-slate-600">
                Quét tự động các đơn <code className="bg-slate-100 px-1 rounded">Shipping</code> quá hạn cam kết giao &gt; 3 ngày (idempotent chống cấp trùng voucher).
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={isRunningOps}
                  onClick={handleScanOverdueOrders}
                  className="px-3 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold cursor-pointer disabled:opacity-50"
                >
                  🔍 Quét đơn trễ ngay
                </button>
                <button
                  type="button"
                  disabled={isRunningOps || delayNotifications.filter((n) => n.status === 'PENDING_SEND').length === 0}
                  onClick={handleDispatchPendingDelay}
                  className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold cursor-pointer disabled:opacity-50 flex items-center gap-1"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Duyệt gửi hàng loạt</span>
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-slate-400">
                    <th className="py-2 px-2">Mã đơn</th>
                    <th className="py-2 px-2">Khách hàng</th>
                    <th className="py-2 px-2">Ngày hẹn giao</th>
                    <th className="py-2 px-2">Trễ</th>
                    <th className="py-2 px-2">Mã Voucher 30k</th>
                    <th className="py-2 px-2">Trạng thái</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {delayNotifications.map((n) => (
                    <tr key={n.order_id} className="hover:bg-slate-50">
                      <td className="py-2 px-2 font-mono font-bold text-slate-800">{n.order_id}</td>
                      <td className="py-2 px-2">{n.customer_name || n.customer_id}</td>
                      <td className="py-2 px-2 font-mono">{n.promised_delivery_date}</td>
                      <td className="py-2 px-2 font-semibold text-rose-600">{n.days_overdue} ngày</td>
                      <td className="py-2 px-2 font-mono text-indigo-700">{n.voucher_code}</td>
                      <td className="py-2 px-2">
                        <Badge variant={n.status === 'SENT' ? 'success' : 'warning'}>{n.status}</Badge>
                      </td>
                    </tr>
                  ))}
                  {delayNotifications.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-slate-400">
                        Chưa có bản ghi đơn trễ nào. Bấm "Quét đơn trễ ngay" để kích hoạt tác tử kiểm tra DB đơn hàng.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Incident Clustering Dashboard */}
          <Card title="🚨 Gom Cụm Sự Vụ Diện Rộng (24h gần nhất)">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              {clusters.map((c) => (
                <div
                  key={c.cluster_id}
                  className={`p-3 rounded-xl border space-y-2 ${
                    c.is_widespread ? 'bg-rose-50/70 border-rose-200' : 'bg-slate-50 border-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-slate-900">{c.issue_topic}</span>
                    <Badge variant={c.is_widespread ? 'danger' : 'info'}>
                      {c.count} lượt {c.is_widespread ? '• Diện rộng' : ''}
                    </Badge>
                  </div>
                  <p className="text-[11px] text-slate-500 font-mono">
                    Intent: {c.predicted_intent} • ID: {c.cluster_id}
                  </p>
                  <ul className="space-y-1 text-[11px] text-slate-700 list-disc pl-4">
                    {c.sample_queries.map((q, idx) => (
                      <li key={idx} className="truncate">{q}</li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    disabled={isRunningOps}
                    onClick={() => handleBroadcastCluster(c)}
                    className="w-full py-1.5 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-[11px] cursor-pointer"
                  >
                    📢 Phát thông báo xử lý hàng loạt
                  </button>
                </div>
              ))}
              {clusters.length === 0 && (
                <p className="text-slate-400 italic col-span-2 py-4 text-center">
                  Chưa ghi nhận cụm sự vụ bất thường nào trong cửa sổ 24 giờ gần nhất.
                </p>
              )}
            </div>
          </Card>
        </div>
      )}

      {activeSubTab === 'overview' && (stats ? (
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
                          {r.timestamp ? formatSystemTimeWithSeconds(r.timestamp, { assumeUtcForNaive: true }) : 'N/A'}
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
      ))}

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
