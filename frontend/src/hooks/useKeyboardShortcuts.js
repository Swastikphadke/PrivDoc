import { useEffect } from 'react';

/**
 * Custom hook to register global keyboard shortcuts for PrivyDoc Review.
 * 
 * Rules:
 * - 'A' / 'a': Approve selected candidate
 * - 'R' / 'r': Reject selected candidate
 * - 'M' / 'm': Trigger manual redaction modal
 * - Never trigger when the user is actively typing in an input, textarea, or contentEditable element.
 */
export function useKeyboardShortcuts({
  onApprove,
  onReject,
  onManualAdd,
  onManualRedact,
  enabled = true,
}) {
  const handleManual = onManualAdd || onManualRedact;

  useEffect(() => {
    if (!enabled) return;

    const handleKeyDown = (event) => {
      // Check if user is typing in form controls
      const target = event.target;
      const isInput =
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable;

      if (isInput) {
        return;
      }

      // Avoid triggering when modifier keys (Ctrl, Alt, Meta) are held
      if (event.ctrlKey || event.altKey || event.metaKey) {
        return;
      }

      const key = event.key.toUpperCase();

      if (key === 'A') {
        event.preventDefault();
        onApprove?.();
      } else if (key === 'R') {
        event.preventDefault();
        onReject?.();
      } else if (key === 'M') {
        event.preventDefault();
        handleManual?.();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onApprove, onReject, handleManual, enabled]);
}
