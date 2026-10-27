import type { InputHTMLAttributes } from "react";

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`w-full rounded-2xl border border-ink/15 bg-white px-4 py-3 text-sm outline-none transition placeholder:text-ink/35 focus:border-plum focus:ring-2 focus:ring-plum/15 focus-visible-ring ${className}`} {...props} />;
}

