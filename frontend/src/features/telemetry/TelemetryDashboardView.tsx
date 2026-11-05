import React, { useState, useEffect } from 'react';
import { Activity, ShieldCheck, Zap, HelpCircle } from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { Card } from '../../components/ui/Card';

export const TelemetryDashboardView: React.FC = () => {
  const [stats, setStats] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const fetchStats = async () => {
      setIsLoading(true);
      try {
        const data = await apiClient.getStats();
        setStats(data);
      } catch (err) {
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchStats();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-800">Thống kê Hiệu năng & An toàn Hệ thống (Telemetry)</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Theo dõi tổng lượt truy vấn, độ trễ thời gian thực và phân bổ các chốt chặn an toàn Guardrails.
        </p>
      </div>

      {stats ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <Card className="!p-4">
              <span className="text-xs text-slate-500">Tổng số truy vấn</span>
              <p className="text-2xl font-bold text-slate-800 mt-1">{stats.total_queries || 0}</p>
            </Card>
            <Card className="!p-4">
              <span className="text-xs text-slate-500">Tỷ lệ tự động duyệt</span>
              <p className="text-2xl font-bold text-emerald-600 mt-1">
                {Math.round((stats.auto_approved_rate || 0) * 100)}%
              </p>
            </Card>
            <Card className="!p-4">
              <span className="text-xs text-slate-500">Tỷ lệ chuyển nhân viên</span>
              <p className="text-2xl font-bold text-amber-600 mt-1">
                {Math.round((stats.escalation_rate || 0) * 100)}%
              </p>
            </Card>
            <Card className="!p-4">
              <span className="text-xs text-slate-500">Độ trễ trung bình</span>
              <p className="text-2xl font-bold text-blue-600 mt-1">{Math.round(stats.avg_latency_ms || 0)} ms</p>
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
              </div>
            </Card>

            <Card title="🛡️ Tác vụ Chốt chặn Guardrails">
              <div className="space-y-2 text-xs">
                {Object.entries(stats.guardrail_actions || {}).map(([action, count]) => (
                  <div key={action} className="flex justify-between items-center p-2 rounded-lg bg-slate-50">
                    <span className="font-semibold text-slate-700">{action}</span>
                    <span className="font-mono text-slate-500">{String(count)} lần</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </>
      ) : (
        <div className="p-8 text-center text-slate-400 text-xs">
          {isLoading ? 'Đang tải dữ liệu telemetry...' : 'Chưa có dữ liệu thống kê.'}
        </div>
      )}
    </div>
  );
};

