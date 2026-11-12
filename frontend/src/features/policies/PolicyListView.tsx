import React, { useState, useEffect } from 'react';
import { Plus, RefreshCw, Edit2, Trash2, Search, FileText, CheckCircle2, XCircle, Eye, Copy, Check } from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { RetrievedDocument } from '../../types';
import { Badge } from '../../components/ui/Badge';
import { Card } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { PolicyFilterPreviewModal } from './PolicyFilterPreviewModal';

export const PolicyListView: React.FC = () => {
  const [policies, setPolicies] = useState<RetrievedDocument[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [isFilterModalOpen, setIsFilterModalOpen] = useState(false);

  // View state
  const [viewingPolicy, setViewingPolicy] = useState<RetrievedDocument | null>(null);
  const [copied, setCopied] = useState(false);

  // Edit state
  const [editingPolicy, setEditingPolicy] = useState<RetrievedDocument | null>(null);
  const [editEffDate, setEditEffDate] = useState('');
  const [editExpDate, setEditExpDate] = useState('');
  const [editType, setEditType] = useState<'permanent' | 'temporary' | 'superseded'>('permanent');

  const fetchPolicies = async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.listPolicies();
      setPolicies(data);
    } catch (err: any) {
      alert(`Lỗi tải chính sách: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicies();
  }, []);

  const handleOpenEdit = (p: RetrievedDocument) => {
    setEditingPolicy(p);
    setEditEffDate(p.effective_date || '');
    setEditExpDate(p.expiration_date || '');
    setEditType(p.policy_type || 'permanent');
  };

  // Dynamic preview for editing modal
  const editComputedStatus = React.useMemo(() => {
    const today = new Date().toISOString().split('T')[0];
    if (editType === 'superseded') {
      return { isActive: false, reason: 'Chính sách đã bị thay thế (superseded).' };
    }
    if (editEffDate && today < editEffDate) {
      return { isActive: false, reason: `Chưa đến ngày áp dụng (${editEffDate}).` };
    }
    if (editExpDate && today > editExpDate) {
      return { isActive: false, reason: `Đã quá hạn ngày ${editExpDate}.` };
    }
    if (editType === 'temporary' && !editExpDate) {
      return { isActive: false, reason: 'Chính sách tạm thời bắt buộc có ngày hết hạn.' };
    }
    return { isActive: true, reason: 'Đang có hiệu lực áp dụng.' };
  }, [editType, editEffDate, editExpDate]);

  const handleSaveEdit = async () => {
    if (!editingPolicy) return;
    try {
      await apiClient.updatePolicy(editingPolicy.doc_id, {
        effective_date: editEffDate || null,
        expiration_date: editExpDate || null,
        policy_type: editType,
      });
      alert(`Đã cập nhật chính sách [${editingPolicy.doc_id}]!`);
      setEditingPolicy(null);
      fetchPolicies();
    } catch (err: any) {
      alert(`Lỗi cập nhật: ${err.message}`);
    }
  };

  const handleDelete = async (docId: string) => {
    if (!window.confirm(`Bạn có chắc chắn muốn xóa chính sách [${docId}]?`)) return;
    try {
      await apiClient.deletePolicy(docId);
      fetchPolicies();
    } catch (err: any) {
      alert(`Lỗi xóa: ${err.message}`);
    }
  };

  const handleSyncActive = async () => {
    try {
      const res = await apiClient.syncActiveStatus();
      alert(`Đồng bộ thành công! Có ${res.result?.updated_count || 0} chính sách đổi trạng thái theo ngày hôm nay.`);
      fetchPolicies();
    } catch (err: any) {
      alert(`Lỗi đồng bộ: ${err.message}`);
    }
  };

  const filtered = policies.filter((p) => {
    const matchSearch =
      p.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.doc_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.content.toLowerCase().includes(searchQuery.toLowerCase());
    const matchCategory = selectedCategory === 'ALL' || (p.category || 'Khác') === selectedCategory;
    return matchSearch && matchCategory;
  });

  return (
    <div className="space-y-6">
      {/* Action Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Quản lý Tri thức & Chính sách</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Trích xuất tự động qua AI, quản lý ngày hiệu lực và tự động chuyển đổi trạng thái (Active / Inactive).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleSyncActive}
            className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Đối soát mốc ngày</span>
          </button>
          <button
            onClick={() => setIsFilterModalOpen(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            <span>Trích xuất chính sách mới</span>
          </button>
        </div>
      </div>

      {/* Filter / Search Bar */}
      <Card>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm kiếm theo mã, tiêu đề, từ khóa hoặc nội dung..."
              className="w-full pl-9 pr-4 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 rounded-xl border border-slate-200 text-xs bg-white text-slate-700"
          >
            <option value="ALL">Tất cả danh mục</option>
            <option value="return_refund">return_refund</option>
            <option value="shipping">shipping</option>
            <option value="warranty">warranty</option>
            <option value="payment">payment</option>
            <option value="promotions">promotions</option>
            <option value="account">account</option>
            <option value="support">support</option>
          </select>
        </div>
      </Card>

      {/* Policies Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-100 text-slate-500 uppercase tracking-wider font-semibold">
              <tr>
                <th className="px-5 py-3.5">Mã tài liệu</th>
                <th className="px-5 py-3.5">Tiêu đề & Danh mục</th>
                <th className="px-5 py-3.5">Loại văn bản</th>
                <th className="px-5 py-3.5">Ngày hiệu lực / Hết hạn</th>
                <th className="px-5 py-3.5">Trạng thái tự động</th>
                <th className="px-5 py-3.5 text-center">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-slate-400">
                    {isLoading ? 'Đang tải dữ liệu chính sách...' : 'Không tìm thấy chính sách phù hợp.'}
                  </td>
                </tr>
              ) : (
                filtered.map((p) => (
                  <tr key={p.doc_id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-3.5 font-mono font-semibold text-slate-900">{p.doc_id}</td>
                    <td className="px-5 py-3.5 max-w-xs">
                      <div className="font-semibold text-slate-800 line-clamp-1">{p.title}</div>
                      <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                        <span className="text-[10px] text-slate-400 uppercase tracking-wide font-medium">{p.category || 'support'}</span>
                        {p.tags && p.tags.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            {p.tags.slice(0, 3).map((tag, tIdx) => (
                              <span key={tIdx} className="text-[10px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 border border-slate-200">
                                #{tag}
                              </span>
                            ))}
                            {p.tags.length > 3 && (
                              <span className="text-[10px] text-slate-400">+{p.tags.length - 3}</span>
                            )}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="capitalize">{p.policy_type}</span>
                    </td>
                    <td className="px-5 py-3.5 space-y-0.5 font-mono text-[11px]">
                      <div>Từ: {p.effective_date || 'N/A'}</div>
                      <div className="text-slate-400">Đến: {p.expiration_date || 'Vô hạn'}</div>
                    </td>
                    <td className="px-5 py-3.5">
                      {p.policy_type === 'superseded' ? (
                        <Badge variant="neutral">Superseded</Badge>
                      ) : p.is_active ? (
                        <Badge variant="success">Active</Badge>
                      ) : (
                        <Badge variant="danger">Inactive</Badge>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-center space-x-2">
                      <button
                        onClick={() => {
                          setViewingPolicy(p);
                          setCopied(false);
                        }}
                        className="p-1.5 hover:bg-blue-50 rounded-lg text-slate-600 hover:text-blue-600 transition-colors cursor-pointer"
                        title="Xem toàn văn bản chính sách"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleOpenEdit(p)}
                        className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-600 hover:text-blue-600 transition-colors cursor-pointer"
                        title="Chỉnh sửa ngày / loại"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(p.doc_id)}
                        className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-600 hover:text-rose-600 transition-colors cursor-pointer"
                        title="Xóa chính sách"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Edit Date Modal */}
      {editingPolicy && (
        <Modal
          isOpen={true}
          onClose={() => setEditingPolicy(null)}
          title={`✏️ Chỉnh sửa mốc ngày [${editingPolicy.doc_id}]`}
        >
          <div className="space-y-4 text-xs">
            <p className="text-slate-600 font-semibold">{editingPolicy.title}</p>

            <div>
              <label className="block text-slate-500 mb-1">Loại văn bản:</label>
              <select
                value={editType}
                onChange={(e) => setEditType(e.target.value as any)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 bg-white"
              >
                <option value="permanent">permanent (Vĩnh viễn)</option>
                <option value="temporary">temporary (Có thời hạn)</option>
                <option value="superseded">superseded (Đã thay thế)</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-500 mb-1">Ngày hiệu lực:</label>
                <input
                  type="date"
                  value={editEffDate}
                  onChange={(e) => setEditEffDate(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200"
                />
              </div>
              <div>
                <label className="block text-slate-500 mb-1">Ngày hết hạn:</label>
                <input
                  type="date"
                  value={editExpDate}
                  onChange={(e) => setEditExpDate(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200"
                />
              </div>
            </div>

            {/* Dynamic Status Preview */}
            <div className={`p-3 rounded-xl border flex items-center gap-2 ${editComputedStatus.isActive
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-rose-50 border-rose-200 text-rose-800'
              }`}>
              {editComputedStatus.isActive ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
              )}
              <span>
                Trạng thái tự động sau khi lưu: <b>{editComputedStatus.isActive ? 'Active' : 'Inactive'}</b> ({editComputedStatus.reason})
              </span>
            </div>

            <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
              <button
                onClick={() => setEditingPolicy(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl"
              >
                Hủy
              </button>
              <button
                onClick={handleSaveEdit}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold shadow-sm"
              >
                Lưu thay đổi & Cập nhật
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* View Full Policy Modal */}
      {viewingPolicy && (
        <Modal
          isOpen={true}
          onClose={() => setViewingPolicy(null)}
          title={`📄 Chi tiết Chính sách [${viewingPolicy.doc_id}]`}
        >
          <div className="space-y-4 text-xs">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                  {viewingPolicy.doc_id}
                </span>
                <span className="text-[10px] text-slate-500 uppercase tracking-wider bg-slate-100 px-2 py-0.5 rounded">
                  {viewingPolicy.category || 'support'}
                </span>
                {viewingPolicy.policy_type === 'superseded' ? (
                  <Badge variant="neutral">Superseded</Badge>
                ) : viewingPolicy.is_active ? (
                  <Badge variant="success">Active</Badge>
                ) : (
                  <Badge variant="danger">Inactive</Badge>
                )}
              </div>
              <h3 className="text-sm font-bold text-slate-800">{viewingPolicy.title}</h3>
            </div>

            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-xl border border-slate-200/80 font-mono text-[11px]">
              <div>
                <span className="text-slate-400 block mb-0.5">Hiệu lực từ:</span>
                <span className="font-semibold text-slate-700">{viewingPolicy.effective_date || 'N/A (Áp dụng ngay)'}</span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Ngày hết hạn:</span>
                <span className="font-semibold text-slate-700">{viewingPolicy.expiration_date || 'Vô hạn (Thường trực)'}</span>
              </div>
            </div>

            {viewingPolicy.tags && viewingPolicy.tags.length > 0 && (
              <div>
                <span className="text-slate-500 font-semibold block mb-1">Thẻ từ khóa (Tags):</span>
                <div className="flex flex-wrap gap-1.5">
                  {viewingPolicy.tags.map((tag, idx) => (
                    <span key={idx} className="px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200 text-[11px] font-medium">
                      #{tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-slate-700 font-bold">Toàn văn quy định chính sách:</span>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(viewingPolicy.content);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  }}
                  className="flex items-center gap-1 text-[11px] text-blue-600 hover:text-blue-700 font-semibold cursor-pointer"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? 'Đã sao chép' : 'Sao chép văn bản'}</span>
                </button>
              </div>
              <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-slate-800 leading-relaxed font-sans text-xs whitespace-pre-wrap max-h-72 overflow-y-auto">
                {viewingPolicy.content}
              </div>
            </div>

            <div className="flex justify-end pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setViewingPolicy(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-semibold transition-colors cursor-pointer text-xs"
              >
                Đóng
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Creation / Filter Modal */}
      <PolicyFilterPreviewModal
        isOpen={isFilterModalOpen}
        onClose={() => setIsFilterModalOpen(false)}
        onSuccess={fetchPolicies}
      />
    </div>
  );
};

