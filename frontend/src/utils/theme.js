/**
 * Central styling and badge system according to PrivyDoc UI/UX Specification.
 */

export const CATEGORY_THEMES = {
  PERSON: {
    label: 'Person',
    badgeClass: 'bg-rose-950/70 text-rose-300 border-rose-800',
    highlightClass: 'bg-rose-500/25 border-b-2 border-rose-500 text-rose-100 hover:bg-rose-500/40',
    borderClass: 'border-rose-500',
    dotColor: 'bg-rose-400',
  },
  EMAIL: {
    label: 'Email',
    badgeClass: 'bg-sky-950/70 text-sky-300 border-sky-800',
    highlightClass: 'bg-sky-500/25 border-b-2 border-sky-500 text-sky-100 hover:bg-sky-500/40',
    borderClass: 'border-sky-500',
    dotColor: 'bg-sky-400',
  },
  PHONE: {
    label: 'Phone',
    badgeClass: 'bg-amber-950/70 text-amber-300 border-amber-800',
    highlightClass: 'bg-amber-500/25 border-b-2 border-amber-500 text-amber-100 hover:bg-amber-500/40',
    borderClass: 'border-amber-500',
    dotColor: 'bg-amber-400',
  },
  ADDRESS: {
    label: 'Address',
    badgeClass: 'bg-purple-950/70 text-purple-300 border-purple-800',
    highlightClass: 'bg-purple-500/25 border-b-2 border-purple-500 text-purple-100 hover:bg-purple-500/40',
    borderClass: 'border-purple-500',
    dotColor: 'bg-purple-400',
  },
  ID_LIKE: {
    label: 'ID-Like',
    badgeClass: 'bg-teal-950/70 text-teal-300 border-teal-800',
    highlightClass: 'bg-teal-500/25 border-b-2 border-teal-500 text-teal-100 hover:bg-teal-500/40',
    borderClass: 'border-teal-500',
    dotColor: 'bg-teal-400',
  },
  MANUAL: {
    label: 'Manual',
    badgeClass: 'bg-cyan-950/70 text-cyan-300 border-cyan-800',
    highlightClass: 'bg-cyan-500/25 border-b-2 border-cyan-500 text-cyan-100 hover:bg-cyan-500/40',
    borderClass: 'border-cyan-500',
    dotColor: 'bg-cyan-400',
  },
  CUSTOM: {
    label: 'Custom',
    badgeClass: 'bg-indigo-950/70 text-indigo-300 border-indigo-800',
    highlightClass: 'bg-indigo-500/25 border-b-2 border-indigo-500 text-indigo-100 hover:bg-indigo-500/40',
    borderClass: 'border-indigo-500',
    dotColor: 'bg-indigo-400',
  },
  DEFAULT: {
    label: 'PII',
    badgeClass: 'bg-slate-800 text-slate-300 border-slate-700',
    highlightClass: 'bg-slate-700/40 border-b-2 border-slate-500 text-slate-100 hover:bg-slate-700/60',
    borderClass: 'border-slate-500',
    dotColor: 'bg-slate-400',
  },
};

export const STATUS_BADGES = {
  PENDING: {
    label: 'Pending',
    className: 'bg-slate-800 text-slate-300 border-slate-700',
  },
  APPROVED: {
    label: 'Approved',
    className: 'bg-emerald-950/80 text-emerald-300 border-emerald-700 font-semibold',
  },
  REJECTED: {
    label: 'Rejected',
    className: 'bg-slate-900/90 text-slate-500 border-slate-800 line-through',
  },
  MANUAL: {
    label: 'Manual',
    className: 'bg-cyan-950/80 text-cyan-300 border-cyan-700 font-semibold',
  },
  NEEDS_REVIEW: {
    label: 'Needs Review',
    className: 'bg-orange-950/80 text-orange-300 border-orange-700',
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
