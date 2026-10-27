import type { ButtonHTMLAttributes } from "react";

export function Button({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`rounded-full bg-plum px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#5931a8] disabled:opacity-50 ${className}`} {...props} />;
}

