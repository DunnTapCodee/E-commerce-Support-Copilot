import React, { useState, useMemo } from 'react';
import { Sparkles, Save, AlertCircle, CheckCircle2 } from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { PolicyFilterResult, RetrievedDocument } from '../../types';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';

interface PolicyFilterPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const PolicyFilterPreviewModal: React.FC<PolicyFilterPreviewModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [rawText, setRawText] = useState('');
  const [categoryHint, setCategoryHint] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [extractedData, setExtractedData] = useState<PolicyFilterResult | null>(null);

  // Form edit states
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('support');
  const [policyType, setPolicyType] = useState<'permanent' | 'temporary' | 'superseded'>('permanent');
  const [effectiveDate, setEffectiveDate] = useState('');
  const [expirationDate, setExpirationDate] = useState('');
  const [tags, setTags] = useState('');
  const [docId, setDocId] = useState('');

  // Handle AI Filter
  const handleRunFilter = async () => {
    if (!rawText.trim()) return;
    setIsLoading(true);
    try {
      const res = await apiClient.filterPolicy(rawText, categoryHint || undefined);
      setExtractedData(res);
      const p = res.extracted_policy;
      setDocId(p.doc_id);
      setTitle(p.title);
      setContent(p.content);
      setCategory(p.category || 'support');
      setPolicyType(p.policy_type || 'permanent');
      setEffectiveDate(p.effective_date || '');
      setExpirationDate(p.expiration_date || '');
      setTags((p.tags || []).join(', '));
    } catch (err: any) {
      alert(`Lỗi phân tích: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Dynamic is_active calculation in real-time
  const computedActiveStatus = useMemo(() => {
    const today = new Date().toISOString().split('T')[0];
    if (policyType === 'superseded') {
      return { isActive: false, reason: 'Chính sách đã bị thay thế (superseded).' };
    }
    if (effectiveDate && today < effectiveDate) {
      return { isActive: false, reason: `Chưa đến ngày áp dụng (${effectiveDate}).` };
    }
    if (expirationDate && today > expirationDate) {
      return { isActive: false, reason: `Đã quá hạn ngày ${expirationDate}.` };
    }
    if (policyType === 'temporary' && !expirationDate) {
      return { isActive: false, reason: 'Chính sách tạm thời cần có ngày hết hạn rõ ràng.' };
    }
    return { isActive: true, reason: 'Đang có hiệu lực áp dụng.' };
  }, [policyType, effectiveDate, expirationDate]);

  const handleSave = async () => {
    if (!title.trim() || !content.trim()) {
      alert('Vui lòng nhập đầy đủ tiêu đề và nội dung.');
      return;
    }

    const newPolicy: RetrievedDocument = {
      doc_id: docId || `POL-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
      title: title.trim(),
      content: content.trim(),
      category,
      policy_type: policyType,
      effective_date: effectiveDate.trim() || null,
      expiration_date: expirationDate.trim() || null,
      tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
      version: '1.0',
      is_active: computedActiveStatus.isActive,
    };

    try {
      await apiClient.createPolicy(newPolicy, `Trích xuất từ AI Filter. Trạng thái tự động: ${computedActiveStatus.isActive}`);
      alert('Đã lưu chính sách vào Knowledge Base thành công!');
      onSuccess();
      onClose();
    } catch (err: any) {
      alert(`Lỗi lưu trữ: ${err.message}`);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="🤖 Trích xuất & Tạo Chính sách bằng AI">
      <div className="space-y-5 text-sm">
        {/* Step 1: Raw Input */}
        <div>
          <label className="block text-xs font-semibold text-slate-700 mb-1.5">
            Dán văn bản chính sách thô của nhân viên:
          </label>
          <textarea
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            rows={4}
            placeholder="Ví dụ: Chính sách bảo hành áp dụng từ 2026-01-01 cho sản phẩm điện tử trong 12 tháng..."
            className="w-full p-3 rounded-xl border border-slate-200 text-xs focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          />
          <div className="mt-2 flex gap-3 items-center">
            <select
              value={categoryHint}
              onChange={(e) => setCategoryHint(e.target.value)}
              className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs bg-white"
            >
              <option value="">Gợi ý danh mục (tự động nếu để trống)</option>
              <option value="return_refund">Đổi trả & Hoàn tiền (return_refund)</option>
              <option value="shipping">Vận chuyển (shipping)</option>
              <option value="warranty">Bảo hành (warranty)</option>
              <option value="payment">Thanh toán (payment)</option>
              <option value="promotions">Khuyến mãi (promotions)</option>
            </select>
            <button
              onClick={handleRunFilter}
              disabled={isLoading || !rawText.trim()}
              className="py-1.5 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{isLoading ? 'Đang phân tích...' : 'Trích xuất thông tin'}</span>
            </button>
          </div>
        </div>

        {/* Step 2: Extracted Fields Review & Edit */}
        {extractedData && (
          <div className="pt-4 border-t border-slate-100 space-y-4 animate-in fade-in">
            <div className="p-3 bg-blue-50 rounded-xl border border-blue-100 text-xs space-y-1">
              <span className="font-semibold text-blue-900 block">Kết quả AI trích xuất:</span>
              {extractedData.warnings.map((w, idx) => (
                <p key={idx} className="text-blue-700">• {w}</p>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Mã định danh (Doc ID):</label>
                <input
                  type="text"
                  value={docId}
                  onChange={(e) => setDocId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Danh mục:</label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs bg-white"
                >
                  <option value="return_refund">return_refund</option>
                  <option value="shipping">shipping</option>
                  <option value="warranty">warranty</option>
                  <option value="payment">payment</option>
                  <option value="promotions">promotions</option>
                  <option value="account">account</option>
                  <option value="support">support</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Tiêu đề chính sách:</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Nội dung chuẩn hóa:</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs font-sans leading-relaxed"
              />
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Loại văn bản:</label>
                <select
                  value={policyType}
                  onChange={(e) => setPolicyType(e.target.value as any)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs bg-white"
                >
                  <option value="permanent">permanent (Vĩnh viễn)</option>
                  <option value="temporary">temporary (Có thời hạn)</option>
                  <option value="superseded">superseded (Đã thay thế)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Ngày hiệu lực:</label>
                <input
                  type="date"
                  value={effectiveDate}
                  onChange={(e) => setEffectiveDate(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Ngày hết hạn:</label>
                <input
                  type="date"
                  value={expirationDate}
                  onChange={(e) => setExpirationDate(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs"
                />
              </div>
            </div>

            {/* Dynamic Status Preview */}
            <div className={`p-3 rounded-xl border flex items-center justify-between text-xs ${computedActiveStatus.isActive
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-rose-50 border-rose-200 text-rose-800'
              }`}>
              <div className="flex items-center gap-2">
                {computedActiveStatus.isActive ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-rose-600" />
                )}
                <span>
                  Trạng thái tự động: <b>{computedActiveStatus.isActive ? 'Active (Hiệu lực)' : 'Inactive (Vô hiệu)'}</b> — {computedActiveStatus.reason}
                </span>
              </div>
            </div>

            <div className="pt-2 flex justify-end gap-2">
              <button
                onClick={onClose}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-medium"
              >
                Hủy bỏ
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-sm"
              >
                <Save className="w-4 h-4" />
                <span>Lưu vào Knowledge Base</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};

