/**
 * Focus Trap Hook
 *
 * Traps focus within a container element for accessibility.
 * Used by modals, dialogs, and other overlay components.
 */

import { useEffect, useRef, useCallback } from 'react';

export function useFocusTrap(enabled: boolean = true) {
  const containerRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (!enabled || event.key !== 'Tab') return;

    const container = containerRef.current;
    if (!container) return;

    const focusableElements = container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (event.shiftKey) {
      if (document.activeElement === firstElement) {
        event.preventDefault();
        lastElement?.focus();
      }
    } else {
      if (document.activeElement === lastElement) {
        event.preventDefault();
        firstElement?.focus();
      }
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;

    // Store previously focused element
    previouslyFocused.current = document.activeElement as HTMLElement;

    // Focus first focusable element
    const container = containerRef.current;
    if (container) {
      const firstFocusable = container.querySelector<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      firstFocusable?.focus();
    }

    const handleKeyDownListener = (event: Event) => {
      handleKeyDown(event as unknown as React.KeyboardEvent);
    };

    document.addEventListener('keydown', handleKeyDownListener);

    return () => {
      document.removeEventListener('keydown', handleKeyDownListener);
      // Restore focus when trap is disabled
      previouslyFocused.current?.focus();
    };
  }, [enabled, handleKeyDown]);

  return containerRef;
}

/**
 * Focus Trap Component
 *
 * Wrapper component that applies focus trapping to its children.
 */
import { ReactNode, KeyboardEvent } from 'react';

interface FocusTrapProps {
  children: ReactNode;
  enabled?: boolean;
  onDeactivate?: () => void;
}

export function FocusTrap({ children, enabled = true, onDeactivate }: FocusTrapProps) {
  const containerRef = useFocusTrap(enabled);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && enabled && onDeactivate) {
      onDeactivate();
    }
  };

  return (
    <div ref={containerRef} onKeyDown={handleKeyDown} role="dialog" aria-modal="true">
      {children}
    </div>
  );
}