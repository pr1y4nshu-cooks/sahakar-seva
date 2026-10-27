import { AlertCircle, LoaderCircle } from "lucide-react";

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return <div className="flex items-center gap-2 text-sm text-ink/60"><LoaderCircle className="animate-spin text-plum" size={16} />{label}</div>;
}

export function ErrorState({ message = "Something went wrong. Please try again." }: { message?: string }) {
  return <div className="flex items-center gap-2 rounded-2xl bg-rose-50 p-4 text-sm text-rose-700"><AlertCircle size={16} />{message}</div>;
}

export function EmptyState({ message = "Nothing to show yet." }: { message?: string }) {
  return <div className="rounded-2xl border border-dashed border-ink/15 p-6 text-center text-sm text-ink/50">{message}</div>;
}

