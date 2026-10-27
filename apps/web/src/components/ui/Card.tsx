import type { HTMLAttributes } from "react";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`rounded-3xl border border-[#e9e3f0] bg-white p-6 shadow-[0_12px_40px_rgba(55,32,91,0.06)] ${className}`} {...props} />;
}

