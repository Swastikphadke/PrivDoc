/**
 * Central Design System Tokens & Security State Themes for PrivyDoc Workstation.
 * Ensures consistent category colors, review state indicators, and verification badges across all views.
 */

export const CATEGORY_THEMES = {
  PERSON: {
    label: 'Person',
    shortCode: 'PER',
    badgeClass: 'bg-rose-950/80 text-rose-300 border-rose-800/80',
    highlightClass: 'bg-rose-500/20 border-b-2 border-rose-500 text-rose-100 hover:bg-rose-500/35',
    borderClass: 'border-rose-500',
    dotColor: 'bg-rose-400',
    barColor: 'bg-rose-500',
  },
  EMAIL: {
    label: 'Email',
    shortCode: 'EML',
    badgeClass: 'bg-sky-950/80 text-sky-300 border-sky-800/80',
    highlightClass: 'bg-sky-500/20 border-b-2 border-sky-500 text-sky-100 hover:bg-sky-500/35',
    borderClass: 'border-sky-500',
    dotColor: 'bg-sky-400',
    barColor: 'bg-sky-500',
  },
  PHONE: {
    label: 'Phone',
    shortCode: 'TEL',
    badgeClass: 'bg-amber-950/80 text-amber-300 border-amber-800/80',
    highlightClass: 'bg-amber-500/20 border-b-2 border-amber-500 text-amber-100 hover:bg-amber-500/35',
    borderClass: 'border-amber-500',
    dotColor: 'bg-amber-400',
    barColor: 'bg-amber-500',
  },
  ADDRESS: {
    label: 'Address',
    shortCode: 'ADR',
    badgeClass: 'bg-purple-950/80 text-purple-300 border-purple-800/80',
    highlightClass: 'bg-purple-500/20 border-b-2 border-purple-500 text-purple-100 hover:bg-purple-500/35',
    borderClass: 'border-purple-500',
    dotColor: 'bg-purple-400',
    barColor: 'bg-purple-500',
  },
  ID_LIKE: {
    label: 'ID-Like',
    shortCode: 'ID',
    badgeClass: 'bg-teal-950/80 text-teal-300 border-teal-800/80',
    highlightClass: 'bg-teal-500/20 border-b-2 border-teal-500 text-teal-100 hover:bg-teal-500/35',
    borderClass: 'border-teal-500',
    dotColor: 'bg-teal-400',
    barColor: 'bg-teal-500',
  },
  MANUAL: {
    label: 'Manual',
    shortCode: 'MAN',
    badgeClass: 'bg-cyan-950/80 text-cyan-300 border-cyan-800/80',
    highlightClass: 'bg-cyan-500/20 border-b-2 border-cyan-500 text-cyan-100 hover:bg-cyan-500/35',
    borderClass: 'border-cyan-500',
    dotColor: 'bg-cyan-400',
    barColor: 'bg-cyan-500',
  },
  CUSTOM: {
    label: 'Custom',
    shortCode: 'CST',
    badgeClass: 'bg-indigo-950/80 text-indigo-300 border-indigo-800/80',
    highlightClass: 'bg-indigo-500/20 border-b-2 border-indigo-500 text-indigo-100 hover:bg-indigo-500/35',
    borderClass: 'border-indigo-500',
    dotColor: 'bg-indigo-400',
    barColor: 'bg-indigo-500',
  },
  DEFAULT: {
    label: 'PII',
    shortCode: 'PII',
    badgeClass: 'bg-slate-800 text-slate-300 border-slate-700',
    highlightClass: 'bg-slate-700/40 border-b-2 border-slate-500 text-slate-100 hover:bg-slate-700/60',
    borderClass: 'border-slate-500',
    dotColor: 'bg-slate-400',
    barColor: 'bg-slate-500',
  },
};

export const STATUS_BADGES = {
  PENDING: {
    label: 'Pending',
    className: 'bg-slate-800/90 text-slate-300 border-slate-700',
  },
  APPROVED: {
    label: 'Approved',
    className: 'bg-emerald-950/80 text-emerald-300 border-emerald-700/80 font-semibold',
  },
  REJECTED: {
    label: 'Rejected',
    className: 'bg-slate-900 text-slate-500 border-slate-800 line-through',
  },
  MANUAL: {
    label: 'Manual',
    className: 'bg-cyan-950/80 text-cyan-300 border-cyan-700/80 font-semibold',
  },
  NEEDS_REVIEW: {
    label: 'Needs Review',
    className: 'bg-amber-950/80 text-amber-300 border-amber-700/80',
  },
};

export const CONFIDENCE_BADGES = {
  HIGH: {
    label: 'High Conf.',
    className: 'text-emerald-400',
    dotClass: 'bg-emerald-400',
  },
  MEDIUM: {
    label: 'Medium Conf.',
    className: 'text-amber-400',
    dotClass: 'bg-amber-400',
  },
  LOW: {
    label: 'Low Conf.',
    className: 'text-slate-400',
    dotClass: 'bg-slate-400',
  },
};

export const EXPORT_STATE_THEMES = {
  VERIFIED: {
    label: 'VERIFIED SAFE',
    badgeClass: 'bg-emerald-950/90 border-emerald-700 text-emerald-300',
    panelClass: 'bg-emerald-950/20 border-emerald-800/70',
  },
  RECONSTRUCTED: {
    label: 'VERIFIED (RECONSTRUCTED)',
    badgeClass: 'bg-cyan-950/90 border-cyan-700 text-cyan-300',
    panelClass: 'bg-cyan-950/20 border-cyan-800/70',
  },
  FAILED: {
    label: 'VERIFICATION FAILED (BLOCKED)',
    badgeClass: 'bg-rose-950/90 border-rose-700 text-rose-300',
    panelClass: 'bg-rose-950/25 border-rose-800/80',
  },
  PROCESSING: {
    label: 'PROCESSING & AUDITING',
    badgeClass: 'bg-sky-950/90 border-sky-700 text-sky-300',
    panelClass: 'bg-sky-950/20 border-sky-800/70',
  },
  UNVERIFIED: {
    label: 'UNVERIFIED (NOT EXPORTED)',
    badgeClass: 'bg-amber-950/80 border-amber-800 text-amber-300',
    panelClass: 'bg-slate-900 border-slate-800',
  },
  PENDING: {
    label: 'PENDING REDACTION',
    badgeClass: 'bg-slate-800 border-slate-700 text-slate-300',
    panelClass: 'bg-slate-900 border-slate-800',
  },
};
