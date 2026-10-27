/**
 * Focus Visible Hook
 *
 * Provides :focus-visible polyfill for better keyboard accessibility.
 * Adds focus-visible class when user navigates via keyboard.
 */

import { useEffect, useRef, useState, useCallback } from 'react';

export function useFocusVisible() {
  const [isFocusVisible, setIsFocusVisible] = useState(false);
  const hadKeyboardEvent = useRef(false);
  const inputTypesWhitelist = {
    text: true,
    search: true,
    email: true,
    password: true,
    number: true,
    tel: true,
    url: true,
  };

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (event.metaKey || event.altKey || event.ctrlKey) return;

    // Only consider these keys for focus-visible
    const focusKeys = ['Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Escape', ' '];
    if (focusKeys.includes(event.key)) {
      hadKeyboardEvent.current = true;
      setIsFocusVisible(true);
    }
  }, []);

  const handlePointerDown = useCallback(() => {
    hadKeyboardEvent.current = false;
    setIsFocusVisible(false);
  }, []);

  const handleFocus = useCallback((event: React.FocusEvent) => {
    const target = event.target as HTMLElement;
    // Check if element is an input with whitelisted type
    let isWhitelistedInput = false;
    if (target instanceof HTMLInputElement) {
      isWhitelistedInput = inputTypesWhitelist[target.type as keyof typeof inputTypesWhitelist];
    }
    if (hadKeyboardEvent.current || isWhitelistedInput) {
      setIsFocusVisible(true);
    }
  }, []);

  const handleBlur = useCallback(() => {
    setIsFocusVisible(false);
  }, []);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [handleKeyDown, handlePointerDown]);

  return {
    isFocusVisible,
    focusProps: {
      onFocus: handleFocus,
      onBlur: handleBlur,
    },
  };
}

/**
 * Hook for applying focus-visible styles to a component
 */
export function useFocusVisibleClass() {
  const { isFocusVisible, focusProps } = useFocusVisible();

  return {
    isFocusVisible,
    focusProps,
    className: isFocusVisible ? 'focus-visible-ring' : '',
  };
}