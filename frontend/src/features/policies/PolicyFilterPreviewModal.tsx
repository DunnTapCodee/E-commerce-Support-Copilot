import React, { useState, useMemo } from 'react';
import {
  Sparkles,
  Save,
  CheckCircle2,
  AlertCircle,
  FileText,
  Upload,
  Trash2,
  Eye,
  Check,
  Plus,
  RotateCcw,
} from 'lucide-react';
import { apiClient } from '../../lib/api-client';
import { PolicyFilterResult, RetrievedDocument } from '../../types';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { extractTextFromFile } from '../../lib/file-parser';

interface PolicyFilterPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export interface ExtractedPolicyItem {
  id: string;
  docId: string;
  title: string;
  content: string;
  category: string;
  policyType: 'permanent' | 'temporary' | 'superseded';
  effectiveDate: string;
  expirationDate: string;
  tagsInput: string;
  version: string;
  warnings: string[];
  isSaved: boolean;
  isSaving: boolean;
}

export const PolicyFilterPreviewModal: React.FC<PolicyFilterPreviewModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  // Input mode: 'text' or 'file'
  const [inputMode, setInputMode] = useState<'text' | 'file'>('text');

  // Multi-input: Array of individual policy text boxes (mỗi ô là 1 chính sách)
  const [textBlocks, setTextBlocks] = useState<string[]>(['']);

  // File upload state
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ name: string; size: number; text: string }>>([]);
  const [categoryHint, setCategoryHint] = useState('');

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [progressMsg, setProgressMsg] = useState('');

  // Extracted items list
  const [items, setItems] = useState<ExtractedPolicyItem[]>([]);
  // Active selected item for detail panel (only 1 can be viewed at a time)
  const [selectedIdx, setSelectedIdx] = useState<number>(0);

  // Bulk save state
  const [isBulkSaving, setIsBulkSaving] = useState(false);

  // Helper: compute active status dynamically
  const computeActiveStatus = (policyType: string, effDate: string, expDate: string) => {
    const today = new Date().toISOString().split('T')[0];
    if (policyType === 'superseded') {
      return { isActive: false, reason: 'Chính sách đã bị thay thế (superseded).' };
    }
    if (effDate && today < effDate) {
      return { isActive: false, reason: `Chưa đến ngày áp dụng (${effDate}).` };
    }
    if (expDate && today > expDate) {
      return { isActive: false, reason: `Đã quá hạn ngày ${expDate}.` };
    }
    if (policyType === 'temporary' && !expDate) {
      return { isActive: false, reason: 'Chính sách tạm thời cần có ngày hết hạn rõ ràng.' };
    }
    return { isActive: true, reason: 'Đang có hiệu lực áp dụng.' };
  };

  // Currently viewed item on the right
  const currentItem = items[selectedIdx] || null;
  const currentStatus = useMemo(() => {
    if (!currentItem) return { isActive: true, reason: '' };
    return computeActiveStatus(currentItem.policyType, currentItem.effectiveDate, currentItem.expirationDate);
  }, [currentItem?.policyType, currentItem?.effectiveDate, currentItem?.expirationDate]);

  // Handle adding another text input box
  const handleAddTextBlock = () => {
    setTextBlocks((prev) => [...prev, '']);
  };

  // Handle changing text of a specific box
  const handleTextBlockChange = (idx: number, val: string) => {
    setTextBlocks((prev) => {
      const updated = [...prev];
      updated[idx] = val;
      return updated;
    });
  };

  // Handle removing a specific text box
  const handleRemoveTextBlock = (idx: number) => {
    if (textBlocks.length <= 1) {
      setTextBlocks(['']);
      return;
    }
    setTextBlocks((prev) => prev.filter((_, i) => i !== idx));
  };

  // Handle sample text filling (fill into separate boxes)
  const handleInsertSampleText = () => {
    setTextBlocks([
      'Chính sách đổi trả hàng hóa tiêu chuẩn áp dụng cho toàn sàn TMĐT từ ngày 01/01/2026. Khách hàng được quyền yêu cầu đổi trả hoặc trả hàng - hoàn tiền trong vòng 15 ngày kể từ ngày nhận hàng thành công nếu sản phẩm có lỗi từ nhà sản xuất, giao sai mẫu mã hoặc bị hư hỏng trong quá trình vận chuyển. Sản phẩm yêu cầu còn nguyên tem mác, chưa qua sử dụng và đầy đủ phụ kiện, hóa đơn đi kèm.',
      'Chính sách bảo hành điện tử chính hãng áp dụng từ 2026-01-01 đến 2026-12-31. Các sản phẩm điện máy và điện thoại được bảo hành miễn phí 12 tháng tại các trung tâm bảo hành ủy quyền trên toàn quốc. Yêu cầu số serial còn rõ ràng, tem bảo hành không bị rách rời hoặc tẩy xóa.',
    ]);
  };

  // Handle multi-format file selection
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setIsProcessing(true);
    setProgressMsg('Đang đọc và chuẩn hóa nội dung các tệp tài liệu...');

    const newFiles: Array<{ name: string; size: number; text: string }> = [];
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        try {
          const text = await extractTextFromFile(file);
          if (text.trim()) {
            newFiles.push({
              name: file.name,
              size: file.size,
              text: text.trim(),
            });
          }
        } catch (err: any) {
          console.error(`Lỗi đọc file ${file.name}:`, err);
        }
      }
      setUploadedFiles((prev) => [...prev, ...newFiles]);
    } finally {
      setIsProcessing(false);
      setProgressMsg('');
      e.target.value = '';
    }
  };

  const handleRemoveFile = (index: number) => {
    setUploadedFiles((prev) => prev.filter((_, idx) => idx !== index));
  };

  // Run AI extraction
  const handleRunExtraction = async () => {
    setIsProcessing(true);
    const newItems: ExtractedPolicyItem[] = [];

    try {
      if (inputMode === 'text') {
        const validBlocks = textBlocks.map((t) => t.trim()).filter(Boolean);
        if (validBlocks.length === 0) {
          alert('Vui lòng nhập nội dung chính sách vào ô trống.');
          setIsProcessing(false);
          return;
        }

        for (let i = 0; i < validBlocks.length; i++) {
          const block = validBlocks[i];
          setProgressMsg(`Đang trích xuất chính sách (${i + 1}/${validBlocks.length})...`);
          try {
            // Use bulk filter to detect any multiple policies or extract standard item
            const results = await apiClient.filterPolicyBulk(block, categoryHint || undefined);
            results.forEach((res, rIdx) => {
              const p = res.extracted_policy;
              newItems.push({
                id: `item-${Date.now()}-${i}-${rIdx}`,
                docId: p.doc_id,
                title: p.title || `Chính sách ${newItems.length + 1}`,
                content: p.content || block,
                category: p.category || 'support',
                policyType: (p.policy_type as any) || 'permanent',
                effectiveDate: p.effective_date || '',
                expirationDate: p.expiration_date || '',
                tagsInput: (p.tags || []).join(', '),
                version: p.version || '1.0',
                warnings: res.warnings || [],
                isSaved: false,
                isSaving: false,
              });
            });
          } catch (err: any) {
            console.error(`Lỗi trích xuất ô ${i + 1}:`, err);
          }
        }
      } else {
        // File mode: process each file and let LLM extract all policies contained within the file
        if (uploadedFiles.length === 0) {
          alert('Vui lòng tải lên ít nhất một tệp tài liệu.');
          setIsProcessing(false);
          return;
        }

        for (let i = 0; i < uploadedFiles.length; i++) {
          const f = uploadedFiles[i];
          setProgressMsg(`Đang phân tích và bóc tách các chính sách trong "${f.name}" (${i + 1}/${uploadedFiles.length})...`);
          try {
            const results = await apiClient.filterPolicyBulk(f.text, categoryHint || undefined);
            results.forEach((res, rIdx) => {
              const p = res.extracted_policy;
              newItems.push({
                id: `item-${Date.now()}-${i}-${rIdx}`,
                docId: p.doc_id,
                title: p.title || `Chính sách ${newItems.length + 1}`,
                content: p.content || f.text,
                category: p.category || 'support',
                policyType: (p.policy_type as any) || 'permanent',
                effectiveDate: p.effective_date || '',
                expirationDate: p.expiration_date || '',
                tagsInput: (p.tags || []).join(', '),
                version: p.version || '1.0',
                warnings: res.warnings || [],
                isSaved: false,
                isSaving: false,
              });
            });
          } catch (err: any) {
            console.error(`Lỗi phân tích file ${f.name}:`, err);
          }
        }
      }

      if (newItems.length === 0) {
        alert('Không trích xuất được chính sách nào từ nội dung đã nạp. Vui lòng kiểm tra lại văn bản.');
      } else {
        setItems(newItems);
        setSelectedIdx(0);
      }
    } finally {
      setIsProcessing(false);
      setProgressMsg('');
    }
  };

  // Update field of the currently viewed item in detail panel
  const updateCurrentItem = (fields: Partial<ExtractedPolicyItem>) => {
    setItems((prev) =>
      prev.map((item, idx) => (idx === selectedIdx ? { ...item, ...fields } : item))
    );
  };

  // Save single policy to KB (policies.json) - Triggered only from list items
  const handleSaveSingle = async (idxToSave: number) => {
    const item = items[idxToSave];
    if (!item || item.isSaved || item.isSaving) return;

    if (!item.title.trim() || !item.content.trim()) {
      alert('Tiêu đề và nội dung chính sách không được để trống.');
      return;
    }

    setItems((prev) =>
      prev.map((it, idx) => (idx === idxToSave ? { ...it, isSaving: true } : it))
    );

    const activeInfo = computeActiveStatus(item.policyType, item.effectiveDate, item.expirationDate);
    const parsedTags = item.tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const newDoc: RetrievedDocument = {
      doc_id: item.docId || `POL-${Math.random().toString(36).substring(2, 9).toUpperCase()}`,
      title: item.title.trim(),
      content: item.content.trim(),
      category: item.category,
      policy_type: item.policyType,
      effective_date: item.effectiveDate.trim() || null,
      expiration_date: item.expirationDate.trim() || null,
      tags: parsedTags,
      version: item.version || '1.0',
      is_active: activeInfo.isActive,
    };

    try {
      await apiClient.createPolicy(
        newDoc,
        `Trích xuất AI Filter từ văn bản. Trạng thái tự động: ${activeInfo.isActive}`
      );

      setItems((prev) =>
        prev.map((it, idx) =>
          idx === idxToSave ? { ...it, isSaved: true, isSaving: false, docId: newDoc.doc_id } : it
        )
      );
      onSuccess();
    } catch (err: any) {
      alert(`Lỗi khi lưu chính sách [${item.docId}]: ${err.message}`);
      setItems((prev) =>
        prev.map((it, idx) => (idx === idxToSave ? { ...it, isSaving: false } : it))
      );
    }
  };

  // Save all unsaved policies to KB
  const handleSaveAll = async () => {
    const unsavedIndices = items
      .map((it, idx) => (!it.isSaved ? idx : -1))
      .filter((idx) => idx !== -1);

    if (unsavedIndices.length === 0) {
      alert('Tất cả chính sách trong danh sách đã được lưu vào KB.');
      return;
    }

    setIsBulkSaving(true);
    for (const idx of unsavedIndices) {
      await handleSaveSingle(idx);
    }
    setIsBulkSaving(false);
  };

  // Reset back to input view
  const handleReset = () => {
    setItems([]);
    setSelectedIdx(0);
  };

  const totalItems = items.length;
  const savedCount = items.filter((it) => it.isSaved).length;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="🤖 Trích xuất & Tạo Chính sách bằng AI"
      maxWidth="6xl"
    >
      <div className="space-y-5 text-xs text-slate-700">
        {/* ========================================================================= */}
        {/* SECTION 1: NGUỒN NHẬP DỮ LIỆU THÔ                                         */}
        {/* ========================================================================= */}
        {items.length === 0 ? (
          <div className="space-y-4">
            {/* Mode Selector Tabs */}
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setInputMode('text')}
                  className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
                    inputMode === 'text'
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>Dán văn bản thô (Từng ô riêng biệt)</span>
                </button>
                <button
                  type="button"
                  onClick={() => setInputMode('file')}
                  className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-semibold transition-all cursor-pointer ${
                    inputMode === 'file'
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  <Upload className="w-3.5 h-3.5" />
                  <span>Tải tệp tài liệu (.docx, .pdf, .txt, .json, ...)</span>
                </button>
              </div>

              {inputMode === 'text' && (
                <button
                  type="button"
                  onClick={handleInsertSampleText}
                  className="text-blue-600 hover:text-blue-700 hover:underline font-medium text-[11px] cursor-pointer"
                >
                  Dán nội dung mẫu (2 ô chính sách)
                </button>
              )}
            </div>

            {/* Mode 1: Individual Text Boxes for each policy with (+) button */}
            {inputMode === 'text' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-700">
                    Danh sách các ô văn bản chính sách ({textBlocks.length}):
                  </span>
                  <span className="text-[11px] text-slate-400">
                    Mỗi ô chứa 1 chính sách riêng biệt. Bấm dấu <b>(+)</b> để thêm ô tiếp theo.
                  </span>
                </div>

                <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
                  {textBlocks.map((blockText, idx) => (
                    <div
                      key={idx}
                      className="p-3 bg-slate-50/70 rounded-2xl border border-slate-200 space-y-1.5 relative"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-blue-700 text-[11px] bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                          Chính sách #{idx + 1}
                        </span>
                        {textBlocks.length > 1 && (
                          <button
                            type="button"
                            onClick={() => handleRemoveTextBlock(idx)}
                            className="text-slate-400 hover:text-rose-600 p-1 rounded-lg hover:bg-rose-50 transition-colors cursor-pointer"
                            title="Xóa ô này"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>

                      <textarea
                        value={blockText}
                        onChange={(e) => handleTextBlockChange(idx, e.target.value)}
                        rows={4}
                        placeholder={`Nhập nội dung cho chính sách #${idx + 1}...`}
                        className="w-full p-3 rounded-xl border border-slate-200 bg-white focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-sans leading-relaxed text-xs"
                      />
                    </div>
                  ))}
                </div>

                {/* Dấu (+) Thêm ô trống mới */}
                <button
                  type="button"
                  onClick={handleAddTextBlock}
                  className="w-full py-2.5 px-4 rounded-xl border-2 border-dashed border-blue-300 hover:border-blue-500 bg-blue-50/50 hover:bg-blue-50 text-blue-700 font-bold flex items-center justify-center gap-1.5 transition-all cursor-pointer"
                >
                  <Plus className="w-4 h-4" />
                  <span>Thêm ô chính sách mới (+)</span>
                </button>
              </div>
            )}

            {/* Mode 2: Multi-format File Upload */}
            {inputMode === 'file' && (
              <div className="space-y-3">
                <div className="border-2 border-dashed border-slate-200 hover:border-blue-400 bg-slate-50/60 hover:bg-blue-50/20 rounded-2xl p-6 text-center transition-all cursor-pointer relative">
                  <input
                    type="file"
                    multiple
                    accept=".txt,.md,.json,.csv,.doc,.docx,.pdf,text/*"
                    onChange={handleFileChange}
                    className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                  />
                  <div className="flex flex-col items-center justify-center gap-2 pointer-events-none">
                    <div className="w-12 h-12 rounded-2xl bg-blue-100 text-blue-600 flex items-center justify-center shadow-sm">
                      <Upload className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="font-bold text-slate-800 text-sm">
                        Kéo thả hoặc bấm để tải lên tệp tài liệu
                      </p>
                      <p className="text-slate-500 text-[11px] mt-0.5">
                        Hỗ trợ <b>mọi định dạng</b>: Word <code>.docx</code>, <code>.pdf</code>, <code>.txt</code>, <code>.json</code>... Hệ thống AI sẽ tự động phân tích và bóc tách thành danh sách các chính sách tương ứng bên trong tệp.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Uploaded Files List */}
                {uploadedFiles.length > 0 && (
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
                    <div className="flex items-center justify-between font-semibold text-slate-700">
                      <span>Các tệp đã tải lên ({uploadedFiles.length}):</span>
                      <button
                        type="button"
                        onClick={() => setUploadedFiles([])}
                        className="text-rose-600 hover:underline text-[11px] cursor-pointer"
                      >
                        Xóa tất cả
                      </button>
                    </div>
                    <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1">
                      {uploadedFiles.map((f, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between p-2 bg-white rounded-lg border border-slate-200 text-[11px]"
                        >
                          <div className="flex items-center gap-2 overflow-hidden">
                            <FileText className="w-4 h-4 text-blue-600 flex-shrink-0" />
                            <span className="font-semibold text-slate-800 truncate">{f.name}</span>
                            <span className="text-slate-400">({(f.size / 1024).toFixed(1)} KB)</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleRemoveFile(idx)}
                            className="text-slate-400 hover:text-rose-600 p-1 cursor-pointer"
                            title="Xóa tệp"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Hint category & Submit Action */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-slate-100">
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <span className="text-slate-500 font-medium">Gợi ý danh mục:</span>
                <select
                  value={categoryHint}
                  onChange={(e) => setCategoryHint(e.target.value)}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs"
                >
                  <option value="">Tự động nhận diện danh mục</option>
                  <option value="return_refund">Đổi trả & Hoàn tiền (return_refund)</option>
                  <option value="shipping">Vận chuyển (shipping)</option>
                  <option value="warranty">Bảo hành (warranty)</option>
                  <option value="payment">Thanh toán (payment)</option>
                  <option value="promotions">Khuyến mãi (promotions)</option>
                  <option value="account">Tài khoản (account)</option>
                  <option value="support">Hỗ trợ chung (support)</option>
                </select>
              </div>

              <button
                type="button"
                onClick={handleRunExtraction}
                disabled={
                  isProcessing ||
                  (inputMode === 'text' && !textBlocks.some((t) => t.trim())) ||
                  (inputMode === 'file' && uploadedFiles.length === 0)
                }
                className="w-full sm:w-auto px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-50 cursor-pointer"
              >
                <Sparkles className="w-4 h-4" />
                <span>{isProcessing ? 'Đang trích xuất với LLM...' : '✨ Trích xuất thông tin'}</span>
              </button>
            </div>

            {isProcessing && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-blue-800 flex items-center gap-2 animate-pulse">
                <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                <span className="font-medium">{progressMsg}</span>
              </div>
            )}
          </div>
        ) : (
          /* ========================================================================= */
          /* SECTION 2: GIAO DIỆN KẾT QUẢ MASTER - DETAIL                              */
          /* ========================================================================= */
          <div className="space-y-4">
            {/* Top Toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-50 rounded-2xl border border-slate-200">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center font-bold text-xs shadow-sm">
                  {totalItems}
                </div>
                <div>
                  <span className="font-bold text-slate-800 text-xs block">
                    Đã trích xuất {totalItems} chính sách từ dữ liệu
                  </span>
                  <span className="text-[11px] text-slate-500">
                    Trạng thái: <b>{savedCount}/{totalItems}</b> chính sách đã lưu vào Knowledge Base
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Nhập đợt khác</span>
                </button>

                {savedCount < totalItems && (
                  <button
                    type="button"
                    onClick={handleSaveAll}
                    disabled={isBulkSaving}
                    className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-bold flex items-center gap-1.5 shadow-sm transition-all disabled:opacity-50 cursor-pointer"
                  >
                    <Save className="w-3.5 h-3.5" />
                    <span>{isBulkSaving ? 'Đang lưu...' : `Lưu tất cả (${totalItems - savedCount}) vào KB`}</span>
                  </button>
                )}
              </div>
            </div>

            {/* Side-by-Side: Left List (Master) + Right Detail Panel */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
              {/* ------------------------------------------------------------- */}
              {/* CỘT TRÁI: DANH SÁCH CHÍNH SÁCH (Đã bỏ Nguồn & bỏ Tags ở bên trái) */}
              {/* ------------------------------------------------------------- */}
              <div className="lg:col-span-5 space-y-2.5 max-h-[68vh] overflow-y-auto pr-1">
                <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider px-1">
                  Danh sách chính sách cần duyệt ({items.length})
                </div>

                {items.map((item, idx) => {
                  const isSelected = selectedIdx === idx;
                  const itemActive = computeActiveStatus(item.policyType, item.effectiveDate, item.expirationDate);

                  return (
                    <div
                      key={item.id}
                      className={`p-3.5 rounded-2xl border transition-all ${
                        isSelected
                          ? 'bg-blue-50/60 border-blue-400 shadow-sm ring-2 ring-blue-500/20'
                          : 'bg-white border-slate-200 hover:border-slate-300'
                      }`}
                    >
                      {/* Item Header */}
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center gap-1.5 overflow-hidden">
                          <span className="font-mono text-[10px] font-bold text-blue-700 bg-blue-100/70 px-2 py-0.5 rounded border border-blue-200 truncate">
                            {item.docId}
                          </span>
                          <span className="text-[10px] font-semibold text-slate-500 uppercase bg-slate-100 px-1.5 py-0.5 rounded">
                            {item.category}
                          </span>
                        </div>
                        {itemActive.isActive ? (
                          <Badge variant="success">Active</Badge>
                        ) : (
                          <Badge variant="danger">Inactive</Badge>
                        )}
                      </div>

                      {/* Policy Title */}
                      <h4 className="font-bold text-slate-800 text-xs mb-3 line-clamp-2 leading-snug">
                        {item.title}
                      </h4>

                      {/* ACTION BUTTONS: Xem chi tiết & Lưu vào KB cạnh nhau */}
                      <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
                        {/* Nút Xem chi tiết */}
                        <button
                          type="button"
                          onClick={() => setSelectedIdx(idx)}
                          className={`flex-1 py-1.5 px-2.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs cursor-pointer ${
                            isSelected
                              ? 'bg-blue-600 text-white shadow-sm'
                              : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                          }`}
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>{isSelected ? 'Đang xem' : 'Xem chi tiết'}</span>
                        </button>

                        {/* Nút Lưu vào KB */}
                        {item.isSaved ? (
                          <button
                            type="button"
                            disabled
                            className="py-1.5 px-3 rounded-xl font-bold flex items-center justify-center gap-1 bg-emerald-50 text-emerald-700 border border-emerald-300 text-xs cursor-default"
                          >
                            <Check className="w-3.5 h-3.5 text-emerald-600" />
                            <span>Đã lưu vào KB</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleSaveSingle(idx)}
                            disabled={item.isSaving}
                            className="py-1.5 px-3 rounded-xl font-bold flex items-center justify-center gap-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs shadow-sm transition-all disabled:opacity-50 cursor-pointer"
                          >
                            <Save className="w-3.5 h-3.5" />
                            <span>{item.isSaving ? 'Đang lưu...' : 'Lưu vào KB'}</span>
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* ------------------------------------------------------------- */}
              {/* CỘT PHẢI: CHI TIẾT TỪNG CHÍNH SÁCH (Đã bỏ chữ subtab & bỏ nút lưu vào KB) */}
              {/* ------------------------------------------------------------- */}
              <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 shadow-sm p-4 space-y-4 max-h-[68vh] overflow-y-auto">
                {currentItem ? (
                  <>
                    {/* Header: Đã bỏ chữ "SUBTAB" và bỏ nút lưu vào KB theo yêu cầu */}
                    <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-blue-600 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                            Chính sách [{selectedIdx + 1}/{totalItems}]
                          </span>
                          <span className="font-mono text-slate-500 text-[11px] font-bold">{currentItem.docId}</span>
                        </div>
                        <h3 className="text-sm font-bold text-slate-800 mt-1">
                          Đối soát & Hiệu chỉnh thông tin chính sách
                        </h3>
                      </div>

                      {currentItem.isSaved && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-xl font-bold text-xs">
                          <Check className="w-3.5 h-3.5 text-emerald-600" />
                          Đã lưu vào KB
                        </span>
                      )}
                    </div>

                    {/* AI Info & Warnings */}
                    {currentItem.warnings && currentItem.warnings.length > 0 && (
                      <div className="p-2.5 bg-blue-50/70 rounded-xl border border-blue-100 text-[11px] space-y-0.5">
                        <span className="font-bold text-blue-900 block">Thông tin từ AI Filter:</span>
                        {currentItem.warnings.map((w, wIdx) => (
                          <p key={wIdx} className="text-blue-700">• {w}</p>
                        ))}
                      </div>
                    )}

                    {/* Field: Doc ID & Category */}
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block font-semibold text-slate-600 mb-1">Mã định danh (Doc ID):</label>
                        <input
                          type="text"
                          value={currentItem.docId}
                          onChange={(e) => updateCurrentItem({ docId: e.target.value })}
                          className="w-full px-3 py-2 rounded-xl border border-slate-200 font-mono text-xs focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                        />
                      </div>
                      <div>
                        <label className="block font-semibold text-slate-600 mb-1">Danh mục:</label>
                        <select
                          value={currentItem.category}
                          onChange={(e) => updateCurrentItem({ category: e.target.value })}
                          className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                        >
                          <option value="return_refund">return_refund (Đổi trả & Hoàn tiền)</option>
                          <option value="shipping">shipping (Vận chuyển & Giao hàng)</option>
                          <option value="warranty">warranty (Bảo hành & Sửa chữa)</option>
                          <option value="payment">payment (Thanh toán & Ví)</option>
                          <option value="promotions">promotions (Khuyến mãi & Voucher)</option>
                          <option value="account">account (Tài khoản & Bảo mật)</option>
                          <option value="support">support (Hỗ trợ chung)</option>
                        </select>
                      </div>
                    </div>

                    {/* Field: Title */}
                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">Tiêu đề chính sách:</label>
                      <input
                        type="text"
                        value={currentItem.title}
                        onChange={(e) => updateCurrentItem({ title: e.target.value })}
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-800 focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                      />
                    </div>

                    {/* Field: Policy Type, Effective Date, Expiration Date */}
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="block font-semibold text-slate-600 mb-1">Loại văn bản:</label>
                        <select
                          value={currentItem.policyType}
                          onChange={(e) => updateCurrentItem({ policyType: e.target.value as any })}
                          className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs"
                        >
                          <option value="permanent">permanent (Vĩnh viễn)</option>
                          <option value="temporary">temporary (Tạm thời)</option>
                          <option value="superseded">superseded (Bị thay thế)</option>
                        </select>
                      </div>
                      <div>
                        <label className="block font-semibold text-slate-600 mb-1">Ngày hiệu lực:</label>
                        <input
                          type="date"
                          value={currentItem.effectiveDate}
                          onChange={(e) => updateCurrentItem({ effectiveDate: e.target.value })}
                          className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs"
                        />
                      </div>
                      <div>
                        <label className="block font-semibold text-slate-600 mb-1">Ngày hết hạn:</label>
                        <input
                          type="date"
                          value={currentItem.expirationDate}
                          onChange={(e) => updateCurrentItem({ expirationDate: e.target.value })}
                          className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs"
                        />
                      </div>
                    </div>

                    {/* Field: Tags Input & Tag Chips (Bên phải vẫn giữ nguyên tags theo yêu cầu) */}
                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">
                        Thẻ từ khóa (Tags - phân cách bằng dấu phẩy):
                      </label>
                      <input
                        type="text"
                        value={currentItem.tagsInput}
                        onChange={(e) => updateCurrentItem({ tagsInput: e.target.value })}
                        placeholder="đổi trả, hoàn tiền, 15 ngày, bảo hành..."
                        className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                      />
                      {/* Render tag chips */}
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {currentItem.tagsInput
                          .split(',')
                          .map((t) => t.trim())
                          .filter(Boolean)
                          .map((tag, tIdx) => (
                            <span
                              key={tIdx}
                              className="px-2 py-0.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 text-[11px] font-semibold"
                            >
                              #{tag}
                            </span>
                          ))}
                      </div>
                    </div>

                    {/* Field: Content */}
                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">Nội dung chuẩn hóa:</label>
                      <textarea
                        value={currentItem.content}
                        onChange={(e) => updateCurrentItem({ content: e.target.value })}
                        rows={6}
                        className="w-full p-3 rounded-xl border border-slate-200 text-xs font-sans leading-relaxed focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                      />
                    </div>

                    {/* Dynamic Status Preview */}
                    <div
                      className={`p-3 rounded-xl border flex items-center gap-2 text-xs ${
                        currentStatus.isActive
                          ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                          : 'bg-rose-50 border-rose-200 text-rose-800'
                      }`}
                    >
                      {currentStatus.isActive ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                      ) : (
                        <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                      )}
                      <span>
                        Trạng thái tự động: <b>{currentStatus.isActive ? 'Active (Hiệu lực)' : 'Inactive (Không áp dụng)'}</b> — {currentStatus.reason}
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="py-20 text-center text-slate-400">
                    <p>Chọn một chính sách ở danh sách bên trái để xem và chỉnh sửa thông tin chi tiết.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
