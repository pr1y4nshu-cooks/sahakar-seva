import { ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, CheckCircle, LocateFixed, MapPin } from 'lucide-react';
import { marketplace, STATUS_STYLES } from '@/lib/marketplace';

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLES[status] ?? 'bg-ink/5 text-ink/60'}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

export function Alert({ kind, children }: { kind: 'error' | 'success' | 'info'; children: ReactNode }) {
  const styles = {
    error: 'bg-rose-50 text-rose-700',
    success: 'bg-emerald-50 text-emerald-700',
    info: 'bg-blue-50 text-blue-700',
  }[kind];
  const Icon = kind === 'success' ? CheckCircle : AlertCircle;
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={`flex items-start gap-2 rounded-xl p-3 text-sm ${styles}`}>
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function Field({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink">{label}</label>
      {children}
      {hint && <p className="text-xs text-ink/50">{hint}</p>}
    </div>
  );
}

const control =
  'w-full rounded-2xl border border-ink/15 bg-white px-4 py-3 text-sm outline-none focus:border-plum focus:ring-2 focus:ring-plum/15 disabled:opacity-50';

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${control} ${props.className ?? ''}`} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={`${control} ${props.className ?? ''}`} />;
}

export type PickedLocation = { locality: string; latitude: number; longitude: number };

/** Locality dropdown with an optional "use my location" button. Works when geolocation is denied. */
export function LocationPicker({ id, value, onChange }: { id: string; value: PickedLocation | null; onChange: (l: PickedLocation) => void }) {
  const { data: localities = [], isError } = useQuery({ queryKey: ['localities'], queryFn: marketplace.localities, staleTime: Infinity });
  const [geoMessage, setGeoMessage] = useState<string | null>(null);

  const useMyLocation = () => {
    if (!('geolocation' in navigator)) {
      setGeoMessage('Your browser does not support location. Pick a locality instead.');
      return;
    }
    setGeoMessage('Locating…');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // Round before it leaves the browser; the server rounds again.
        onChange({
          locality: 'Current location (approx.)',
          latitude: Math.round(pos.coords.latitude * 1000) / 1000,
          longitude: Math.round(pos.coords.longitude * 1000) / 1000,
        });
        setGeoMessage('Using your approximate current location.');
      },
      () => setGeoMessage('Location permission denied. Pick a locality from the list instead.'),
      { timeout: 10000 },
    );
  };

  const selected = localities.find((l) => l.name === value?.locality)?.slug ?? '';
  return (
    <div className="space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <MapPin className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={16} aria-hidden="true" />
          <Select
            id={id}
            className="pl-9"
            value={selected}
            onChange={(e) => {
              const l = localities.find((x) => x.slug === e.target.value);
              if (l) onChange({ locality: l.name, latitude: l.latitude, longitude: l.longitude });
            }}
          >
            <option value="">{value && !selected ? value.locality : 'Choose a locality…'}</option>
            {localities.map((l) => (
              <option key={l.slug} value={l.slug}>{l.name}, {l.city}</option>
            ))}
          </Select>
        </div>
        <button
          type="button"
          onClick={useMyLocation}
          className="flex items-center justify-center gap-1.5 rounded-full border border-ink/15 bg-white px-4 py-2.5 text-sm font-medium text-ink hover:bg-ink/5"
        >
          <LocateFixed size={15} aria-hidden="true" /> Use my location
        </button>
      </div>
      {isError && <p className="text-xs text-rose-600">Could not load localities from the server.</p>}
      {geoMessage && <p className="text-xs text-ink/60">{geoMessage}</p>}
    </div>
  );
}

export function SimulatedPaymentBanner({ label }: { label: string }) {
  return (
    <p className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-bold uppercase tracking-wide text-amber-800">
      {label}
    </p>
  );
}

/** Convert a <input type="datetime-local"> value (local time) into an ISO string with offset. */
export function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}
