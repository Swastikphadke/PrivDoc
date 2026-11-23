import React, { useState, useEffect } from 'react';
import { ShieldAlert, X, Check, Scissors } from 'lucide-react';
import { CATEGORY_THEMES } from '../../utils/theme';

const CATEGORIES = [
  { value: 'PERSON', label: 'Person', desc: 'Names, initials, signatures' },
  { value: 'EMAIL', label: 'Email', desc: 'Email addresses and obfuscations' },
  { value: 'PHONE', label: 'Phone', desc: 'Mobile, landline, international' },
  { value: 'ADDRESS', label: 'Address', desc: 'Street, postal, locality' },
  { value: 'ID_LIKE', label: 'ID-Like', desc: 'Account numbers, employee/gov IDs' },
];

export default function ManualRedactionModal({
  isOpen,
  onClose,
  onSubmit,
  selection,
}) {
  const [selectedType, setSelectedType] = useState('PERSON');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setSelectedType('PERSON');
    }
  }, [isOpen]);

  if (!isOpen || !selection) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isSubmitting) return;

    try {
      setIsSubmitting(true);
      await onSubmit({
        start: selection.start,
        end: selection.end,
        type: selectedType,
        pageNumber: selection.pageNumber || null,
        bbox: selection.bbox || null,
      });
      onClose();
    } catch (err) {
      console.error('Failed to create manual redaction:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
      <div
        className="w-full max-w-md rounded-xl bg-slate-900 border border-slate-800 shadow-2xl p-6 space-y-5"
        role="dialog"
        aria-modal="true"
        aria-labelledby="manual-redaction-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-sky-950 border border-sky-800/80 text-sky-400">
              <Scissors className="w-4 h-4" />
            </div>
            <div>
              <h3 id="manual-redaction-title" className="text-base font-bold text-white">
                Manual Redaction
              </h3>
              <p className="text-xs text-slate-400">Assign a PII category to the selected span</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
            aria-label="Close modal"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Selected text preview */}
        <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1.5">
          <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
            <span>Canonical Offsets:</span>
            <span className="text-sky-400 font-semibold">
              [{selection.start}, {selection.end}) • {selection.end - selection.start} chars
            </span>
          </div>
          <div className="p-2 rounded bg-slate-900 border border-slate-800 font-mono text-xs text-slate-200 break-all select-all">
            "{selection.text}"
          </div>
        </div>

        {/* Category Selection */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-300">
              PII Category
            </label>
            <div className="grid grid-cols-1 gap-2 max-h-48 overflow-y-auto pr-1">
              {CATEGORIES.map((cat) => {
                const isSelected = selectedType === cat.value;
                const theme = CATEGORY_THEMES[cat.value];
                return (
                  <label
                    key={cat.value}
                    className={`flex items-center justify-between p-2.5 rounded-lg border text-xs cursor-pointer transition ${
                      isSelected
                        ? 'bg-sky-950/40 border-sky-600 text-white shadow-sm'
                        : 'bg-slate-950 border-slate-800 text-slate-300 hover:bg-slate-800/60'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="category"
                        value={cat.value}
                        checked={isSelected}
                        onChange={(e) => setSelectedType(e.target.value)}
                        className="text-sky-500 focus:ring-sky-500"
                      />
                      <div>
                        <span className={`font-semibold mr-1.5 ${theme?.badgeClass || ''}`}>
                          {cat.label}
                        </span>
                        <span className="text-slate-500 text-[11px]">{cat.desc}</span>
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition shadow-lg shadow-emerald-600/20 disabled:opacity-50"
            >
              <Check className="w-3.5 h-3.5" />
              <span>{isSubmitting ? 'Creating...' : 'Add & Approve Redaction'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
