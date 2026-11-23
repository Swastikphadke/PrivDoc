import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useKeyboardShortcuts } from './useKeyboardShortcuts';

describe('useKeyboardShortcuts Hook', () => {
  let onApprove;
  let onReject;
  let onManualRedact;

  beforeEach(() => {
    onApprove = vi.fn();
    onReject = vi.fn();
    onManualRedact = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('triggers onApprove when key "a" or "A" is pressed on body', () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onApprove,
        onReject,
        onManualRedact,
      })
    );

    const event = new KeyboardEvent('keydown', { key: 'a', bubbles: true });
    window.dispatchEvent(event);

    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onReject).not.toHaveBeenCalled();
    expect(onManualRedact).not.toHaveBeenCalled();
  });

  it('triggers onReject when key "r" or "R" is pressed', () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onApprove,
        onReject,
        onManualRedact,
      })
    );

    const event = new KeyboardEvent('keydown', { key: 'R', bubbles: true });
    window.dispatchEvent(event);

    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onApprove).not.toHaveBeenCalled();
    expect(onManualRedact).not.toHaveBeenCalled();
  });

  it('triggers onManualRedact when key "m" or "M" is pressed', () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onApprove,
        onReject,
        onManualRedact,
      })
    );

    const event = new KeyboardEvent('keydown', { key: 'm', bubbles: true });
    window.dispatchEvent(event);

    expect(onManualRedact).toHaveBeenCalledTimes(1);
  });

  it('does NOT trigger shortcuts when typing inside an input element', () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onApprove,
        onReject,
        onManualRedact,
      })
    );

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    const event = new KeyboardEvent('keydown', { key: 'a', bubbles: true });
    input.dispatchEvent(event);

    expect(onApprove).not.toHaveBeenCalled();
    expect(onReject).not.toHaveBeenCalled();
    expect(onManualRedact).not.toHaveBeenCalled();

    document.body.removeChild(input);
  });

  it('does NOT trigger shortcuts when typing inside a textarea element', () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onApprove,
        onReject,
        onManualRedact,
      })
    );

    const textarea = document.createElement('textarea');
    document.body.appendChild(textarea);
    textarea.focus();

    const event = new KeyboardEvent('keydown', { key: 'r', bubbles: true });
    textarea.dispatchEvent(event);

    expect(onReject).not.toHaveBeenCalled();

    document.body.removeChild(textarea);
  });

  it('does NOT trigger shortcuts when ctrl, meta, or alt keys are pressed', () => {
    renderHook(() =>
      useKeyboardShortcuts({
        onApprove,
        onReject,
        onManualRedact,
      })
    );

    const event = new KeyboardEvent('keydown', { key: 'a', ctrlKey: true, bubbles: true });
    window.dispatchEvent(event);

    expect(onApprove).not.toHaveBeenCalled();
  });
});
