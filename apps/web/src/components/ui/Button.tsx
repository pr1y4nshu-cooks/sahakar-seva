import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: 'bg-plum text-white hover:bg-[#5931a8]',
  secondary: 'bg-ink/10 text-ink hover:bg-ink/20',
  outline: 'border border-ink/20 bg-white text-ink hover:bg-ink/5',
  ghost: 'bg-transparent text-ink hover:bg-ink/5',
};

const focusStyles = 'focus-visible-ring';

export function Button({ className = "", variant = 'primary', ...props }: ButtonProps) {
  const baseStyles = 'rounded-full px-5 py-3 text-sm font-semibold transition disabled:opacity-50';
  const variantStyle = variantStyles[variant] ?? variantStyles.primary;
  return <button className={`${baseStyles} ${variantStyle} ${focusStyles} ${className}`} {...props} />;
}

