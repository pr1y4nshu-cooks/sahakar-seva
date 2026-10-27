/**
 * Development Mode Badge
 *
 * Shows when app is running in fixtures mode.
 * Click to view mode details.
 */

import { useState } from 'react';
import { Info, Bug, X, ExternalLink } from 'lucide-react';
import { getApiModeBadge } from '@/lib/api-adapter';
import { Card } from './Card';

export function DevBadge() {
  const [isOpen, setIsOpen] = useState(false);
  const badge = getApiModeBadge();

  if (badge.variant === 'prod') {
    return null;
  }
  if (badge.variant === 'local-identity') {
    return (
      <div className="fixed bottom-4 left-4 z-40 rounded-full border border-amber-300 bg-amber-100 px-3 py-2 text-xs font-medium text-amber-800 shadow-lg" role="status">
        {badge.text}
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 left-4 z-40">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 bg-amber-100 border border-amber-300 rounded-full text-amber-800 text-xs font-medium shadow-lg hover:bg-amber-200 transition-colors"
        aria-label={`Development mode: ${badge.text}`}
      >
        <Bug className="h-3 w-3" />
        <span>{badge.text}</span>
        <Info className="h-3 w-3" />
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-30 bg-black/20" onClick={() => setIsOpen(false)} />
      )}

      {isOpen && (
        <div className="fixed bottom-16 left-4 z-40 w-72 animate-slide-up">
          <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-semibold text-ink">Development Mode</h4>
              <button onClick={() => setIsOpen(false)} className="text-ink/50 hover:text-ink">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2 text-sm text-ink/70">
              <p>The app is running with <strong>development fixtures</strong> instead of a real backend.</p>
              <p>All API calls return simulated data with realistic delays.</p>
              <div className="pt-2 border-t border-ink/10 space-y-1">
                <p className="font-medium">To enable real backend:</p>
                <ol className="list-decimal list-inside space-y-1 ml-2">
                  <li>Set <code className="bg-ink/10 px-1 rounded text-xs">VITE_API_BASE_URL</code></li>
                  <li>Set <code className="bg-ink/10 px-1 rounded text-xs">VITE_SUPABASE_URL</code></li>
                  <li>Set <code className="bg-ink/10 px-1 rounded text-xs">VITE_SUPABASE_ANON_KEY</code></li>
                </ol>
              </div>
              <p className="text-xs text-ink/50">See <code>.env.example</code> for required variables.</p>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}