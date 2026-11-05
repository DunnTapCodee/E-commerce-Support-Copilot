import React, { useState, useEffect } from 'react';
import { Bell, RotateCcw, Eye, RefreshCw, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { PolicyAuditLogEntry } from '../../types';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';

export const AuditNotificationView: React.FC = () => {
  const [logs, setLogs] = useState<PolicyAuditLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedDiffLog, setSelectedDiffLog] = useState<PolicyAuditLogEntry | null>(null);

  const fetchLogs = async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.listAuditLogs();
      setLogs(data);
    } catch (err: any) {
      alert(`Lỗi tải nhật ký: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const handleRollback = async (logId: string, docId: string) => {
    if (!window.confirm(`Bạn có chắc chắn muốn hoàn tác chính sách [${docId}] về phiên bản ghi nhận tại log ${logId}?`)) return;
    try {
      await apiClient.rollbackPolicy(logId);
      alert(`Đã hoàn tác chính sách [${docId}] thành công!`);
      fetchLogs();
    } catch (err: any) {
      alert(`Lỗi hoàn tác: ${err.message}`);
    }
  };

  const getActionBadge = (action: string) => {
    switch (action) {
      case 'CREATE':
        return <Badge variant="success">Tạo mới</Badge>;
      case 'UPDATE':
        return <Badge variant="warning">Chỉnh sửa</Badge>;
      case 'AUTO_EXPIRE':
        return <Badge variant="danger">Tự động hết hạn</Badge>;
      case 'AUTO_ACTIVATE':
        return <Badge variant="success">Tự động kích hoạt</Badge>;
      case 'SUPERSEDE':
        return <Badge variant="neutral">Thay thế</Badge>;
      case 'ROLLBACK':
        return <Badge variant="info">Hoàn tác Rollback</Badge>;
      case 'DELETE':
        return <Badge variant="danger">Xóa tài liệu</Badge>;
      default:
        return <Badge variant="neutral">{action}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-blue-50 text-blue-600 rounded-xl">
            <Bell className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-800">Thông báo & Lịch sử Biến động Tài liệu</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Toàn bộ thay đổi về ngày hiệu lực, hết hạn, tạo mới hoặc tự động hóa hệ thống đều được ghi nhận tức thì.
            </p>
          </div>
        </div>

        <button
          onClick={fetchLogs}
          disabled={isLoading}
          className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Làm mới thông báo</span>
        </button>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card className="!p-4">
          <span className="text-xs text-slate-500">Tổng số biến động</span>
          <p className="text-2xl font-bold text-slate-800 mt-1">{logs.length}</p>
        </Card>
        <Card className="!p-4">
          <span className="text-xs text-slate-500">Nhân viên sửa đổi</span>
          <p className="text-2xl font-bold text-amber-600 mt-1">
            {logs.filter((l) => ['CREATE', 'UPDATE', 'SUPERSEDE'].includes(l.action)).length}
          </p>
        </Card>
        <Card className="!p-4">
          <span className="text-xs text-slate-500">Tự động hóa hệ thống (Auto)</span>
          <p className="text-2xl font-bold text-emerald-600 mt-1">
            {logs.filter((l) => ['AUTO_EXPIRE', 'AUTO_ACTIVATE'].includes(l.action)).length}
          </p>
        </Card>
        <Card className="!p-4">
          <span className="text-xs text-slate-500">Lượt hoàn tác (Rollback)</span>
          <p className="text-2xl font-bold text-blue-600 mt-1">
            {logs.filter((l) => l.action === 'ROLLBACK').length}
          </p>
        </Card>
      </div>

      {/* Notification Feed */}
      <div className="space-y-3">
        {logs.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-slate-400 text-xs">
            {isLoading ? 'Đang tải thông báo...' : 'Chưa có thông báo biến động tài liệu nào.'}
          </div>
        ) : (
          logs.map((log) => (
            <div
              key={log.log_id}
              className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:border-slate-300 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  {getActionBadge(log.action)}
                  <span className="font-mono text-xs font-bold text-slate-800">[{log.doc_id}]</span>
                  <span className="text-xs font-semibold text-slate-700">{log.doc_title || 'Tài liệu'}</span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">{log.reason || 'Cập nhật tài liệu'}</p>
                <div className="flex items-center gap-3 text-[11px] text-slate-400">
                  <span>⏱️ {log.timestamp}</span>
                  <span>•</span>
                  <span>👤 Thực hiện bởi: <b className="text-slate-600">{log.performed_by}</b></span>
                  <span>•</span>
                  <span className="font-mono text-[10px]">ID: {log.log_id}</span>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => setSelectedDiffLog(log)}
                  className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors"
                >
                  <Eye className="w-3.5 h-3.5" />
                  <span>Xem Diff</span>
                </button>
                {log.before_snapshot && log.action !== 'ROLLBACK' && (
                  <button
                    onClick={() => handleRollback(log.log_id, log.doc_id)}
                    className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Rollback</span>
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Diff Modal */}
      {selectedDiffLog && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedDiffLog(null)}
          title={`🔍 So sánh thay đổi (Before vs After) — [${selectedDiffLog.doc_id}]`}
        >
          <div className="space-y-4 text-xs">
            <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
              <p className="font-semibold text-slate-800">Lý do thay đổi:</p>
              <p className="text-slate-600 mt-0.5">{selectedDiffLog.reason || 'Không có ghi chú'}</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="font-semibold text-slate-700 block mb-2">Trạng thái trước thay đổi (Before):</span>
                {selectedDiffLog.before_snapshot ? (
                  <pre className="p-3 bg-slate-900 text-slate-100 rounded-xl overflow-x-auto text-[11px] leading-relaxed">
                    {JSON.stringify(
                      {
                        title: selectedDiffLog.before_snapshot.title,
                        is_active: selectedDiffLog.before_snapshot.is_active,
                        policy_type: selectedDiffLog.before_snapshot.policy_type,
                        effective_date: selectedDiffLog.before_snapshot.effective_date,
                        expiration_date: selectedDiffLog.before_snapshot.expiration_date,
                      },
                      null,
                      2
                    )}
                  </pre>
                ) : (
                  <p className="p-3 bg-slate-100 rounded-xl text-slate-400 italic">Không có dữ liệu trước (Tài liệu tạo mới)</p>
                )}
              </div>

              <div>
                <span className="font-semibold text-slate-700 block mb-2">Trạng thái sau thay đổi (After):</span>
                {selectedDiffLog.after_snapshot ? (
                  <pre className="p-3 bg-slate-900 text-emerald-300 rounded-xl overflow-x-auto text-[11px] leading-relaxed">
                    {JSON.stringify(
                      {
                        title: selectedDiffLog.after_snapshot.title,
                        is_active: selectedDiffLog.after_snapshot.is_active,
                        policy_type: selectedDiffLog.after_snapshot.policy_type,
                        effective_date: selectedDiffLog.after_snapshot.effective_date,
                        expiration_date: selectedDiffLog.after_snapshot.expiration_date,
                      },
                      null,
                      2
                    )}
                  </pre>
                ) : (
                  <p className="p-3 bg-rose-50 border border-rose-100 rounded-xl text-rose-600 italic">Đã xóa tài liệu</p>
                )}
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

