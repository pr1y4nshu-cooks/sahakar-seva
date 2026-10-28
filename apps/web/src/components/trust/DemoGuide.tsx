import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronUp, FlaskConical } from 'lucide-react';
import { authMode } from '@/lib/api-adapter';
import { useAuth } from '@/lib/auth';
import { publicApi } from '@/lib/trust';

/** Development-only presentation guide. It can only appear when the app is in the local dev-identity mode AND the
 *  API has a synthetic dataset. "Switching persona" signs out and opens the real login with the email prefilled:
 *  there is no client-side impersonation, and the passcode is never stored or shown here. */
export function DemoGuide() {
  const [open, setOpen] = useState(false);
  const { user, signOut } = useAuth();
  const guide = useQuery({ queryKey: ['demo-guide'], queryFn: publicApi.demoGuide, enabled: authMode === 'dev', retry: false, staleTime: 120_000 });
  if (authMode !== 'dev' || !guide.data?.enabled) return null;
  const g = guide.data;
  const anchored = g.external_anchoring.checkpoints_by_status['EXTERNALLY_ANCHORED'] ?? 0;
  const total = Object.values(g.external_anchoring.checkpoints_by_status).reduce((a, b) => a + b, 0);
  return (
    <aside aria-label="Demo guide" className="fixed bottom-3 left-3 z-40 w-[min(22rem,calc(100vw-1.5rem))] text-xs" data-testid="demo-guide">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-2 rounded-full border border-plum/30 bg-white px-3 py-2 font-semibold text-plum shadow">
        <span className="flex items-center gap-1.5"><FlaskConical size={14} aria-hidden="true" />Demo guide</span>{open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>
      {open && (
        <div className="mt-2 max-h-[70vh] space-y-3 overflow-y-auto rounded-2xl border border-plum/20 bg-white p-3 shadow-lg">
          <p className="font-semibold text-ink">{g.label}</p>
          <p className="text-ink/60">{g.synthetic_note}</p>
          <ol className="list-decimal space-y-1 pl-4">
            {g.steps.map((s) => <li key={s.title}><Link to={s.route} className="font-semibold text-plum underline">{s.title}</Link><span className="block text-ink/55">{s.hint}</span></li>)}
          </ol>
          <div>
            <p className="font-semibold text-ink">Demo accounts {user ? <span className="font-normal text-ink/50">(signed in as {user.email})</span> : null}</p>
            <ul className="mt-1 space-y-1">
              {g.personas.map((p) => (
                <li key={p.email}>
                  <button type="button" className="text-left font-semibold text-plum underline"
                    onClick={async () => { if (user) await signOut(); window.location.assign(`/login?as=${encodeURIComponent(p.email)}`); }}>{p.name}</button>
                  <span className="block text-ink/55">{p.role}</span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-ink/55">{g.passcode_note}</p>
          </div>
          <p className="text-ink/60" data-testid="guide-anchoring">External timestamps: {g.external_anchoring.tsa_configured ? `${anchored} of ${total} checkpoints verified from ${g.external_anchoring.tsa_name}` : 'not configured (local integrity only)'}. Payments are simulated.</p>
          <Link to="/demo" className="font-semibold text-plum underline">Showcase bookings &amp; tamper demo</Link>
        </div>
      )}
    </aside>
  );
}
