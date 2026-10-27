import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarClock, Loader2, MapPinned, Trash2, Wallet, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { errorMessage, marketplace, RADII, rupees, timeRange } from '@/lib/marketplace';
import { Alert, Field, LocationPicker, PickedLocation, Select, SimulatedPaymentBanner, StatusPill, localInputToIso } from './common';

function SectionTitle({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return (
    <div className="mb-4">
      <h2 className="flex items-center gap-2 text-xl font-bold text-ink">{icon}{title}</h2>
      <p className="mt-1 text-sm text-ink/60">{subtitle}</p>
    </div>
  );
}

export function SkillsSection() {
  const qc = useQueryClient();
  const categories = useQuery({ queryKey: ['categories'], queryFn: marketplace.categories, staleTime: 300_000 });
  const skills = useQuery({ queryKey: ['skills', 'all'], queryFn: () => marketplace.skills(), staleTime: 300_000 });
  const mine = useQuery({ queryKey: ['my-skills'], queryFn: marketplace.mySkills });
  const refresh = () => qc.invalidateQueries({ queryKey: ['my-skills'] });
  const add = useMutation({ mutationFn: marketplace.addSkill, onSuccess: refresh });
  const remove = useMutation({ mutationFn: marketplace.removeSkill, onSuccess: refresh });
  const declared = new Set((mine.data ?? []).map((w) => w.skill.id));
  const busy = add.isPending || remove.isPending;

  return (
    <Card>
      <SectionTitle icon={<Wrench size={20} className="text-plum" />} title="Skills you offer"
        subtitle="Choose the in-person services you can do. These are self-declared — the platform has not checked them." />
      {(mine.isLoading || skills.isLoading) && <Loader2 className="h-5 w-5 animate-spin text-plum" aria-label="Loading skills" />}
      {(mine.isError || skills.isError) && <Alert kind="error">Could not load skills: {errorMessage(mine.error ?? skills.error)}</Alert>}
      <div className="space-y-4">
        {(categories.data ?? []).map((cat) => (
          <fieldset key={cat.id}>
            <legend className="mb-2 text-sm font-semibold text-ink">{cat.name}</legend>
            <div className="flex flex-wrap gap-2">
              {(skills.data ?? []).filter((s) => s.category_id === cat.id).map((s) => {
                const on = declared.has(s.id);
                return (
                  <button key={s.id} type="button" disabled={busy} aria-pressed={on}
                    onClick={() => (on ? remove.mutate(s.id) : add.mutate(s.id))}
                    className={`rounded-full border px-3 py-1.5 text-sm transition disabled:opacity-50 ${on ? 'border-plum bg-plum text-white' : 'border-ink/15 bg-white text-ink hover:bg-ink/5'}`}>
                    {on ? '✓ ' : '+ '}{s.name}
                  </button>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>
      {(mine.data ?? []).length > 0 && (
        <p className="mt-4 text-xs text-ink/60">
          Declared: {(mine.data ?? []).map((w) => `${w.skill.name}${w.skill.is_active ? '' : ' (no longer offered)'}`).join(', ')} · <span className="font-semibold">Self-declared skill</span>
        </p>
      )}
      {(add.isError || remove.isError) && <div className="mt-3"><Alert kind="error">{errorMessage(add.error ?? remove.error)}</Alert></div>}
    </Card>
  );
}

export function ServiceAreaSection() {
  const qc = useQueryClient();
  const current = useQuery({
    queryKey: ['service-settings'],
    queryFn: marketplace.serviceSettings,
    retry: (n, e: any) => e?.status !== 404 && n < 2,
  });
  const [location, setLocation] = useState<PickedLocation | null>(null);
  const [radius, setRadius] = useState<number>(5);
  const [rate, setRate] = useState<string>('300');

  useEffect(() => {
    if (current.data) {
      setLocation({ locality: current.data.locality, latitude: current.data.latitude, longitude: current.data.longitude });
      setRadius(current.data.radius_km);
      setRate(String(current.data.hourly_rate_paise / 100));
    }
  }, [current.data]);

  const save = useMutation({
    mutationFn: () => marketplace.saveServiceSettings({
      locality: location!.locality, latitude: location!.latitude, longitude: location!.longitude,
      radius_km: radius, hourly_rate_paise: Math.round(Number(rate) * 100),
    }),
    onSuccess: (data) => qc.setQueryData(['service-settings'], data),
  });
  const rateValid = Number(rate) >= 10 && Number(rate) <= 10000;

  return (
    <Card>
      <SectionTitle icon={<MapPinned size={20} className="text-plum" />} title="Service area and rate"
        subtitle="Where you work and what you charge. Customers see your locality and approximate distance, never your exact location." />
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (location && rateValid) save.mutate(); }}>
        <Field label="Service centre" htmlFor="svc-loc"><LocationPicker id="svc-loc" value={location} onChange={setLocation} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Service radius" htmlFor="svc-radius">
            <Select id="svc-radius" value={radius} onChange={(e) => setRadius(Number(e.target.value))}>
              {RADII.map((r) => <option key={r} value={r}>{r} km</option>)}
            </Select>
          </Field>
          <Field label="Hourly rate (₹)" htmlFor="svc-rate" hint="Between ₹10 and ₹10,000 per hour.">
            <Input id="svc-rate" type="number" min={10} max={10000} step="1" value={rate} onChange={(e) => setRate(e.target.value)} />
          </Field>
        </div>
        {current.data && <p className="text-xs text-ink/50">{current.data.privacy_note}</p>}
        {save.isError && <Alert kind="error">{errorMessage(save.error)}</Alert>}
        {save.isSuccess && <Alert kind="success">Service area saved.</Alert>}
        <Button type="submit" disabled={!location || !rateValid || save.isPending}>
          {save.isPending ? 'Saving…' : current.data ? 'Update service area' : 'Save service area'}
        </Button>
      </form>
    </Card>
  );
}

export function AvailabilitySection() {
  const qc = useQueryClient();
  const slots = useQuery({ queryKey: ['my-slots'], queryFn: marketplace.mySlots });
  const [start, setStart] = useState('');
  const [hours, setHours] = useState('2');
  const refresh = () => qc.invalidateQueries({ queryKey: ['my-slots'] });
  const add = useMutation({
    mutationFn: () => {
      const s = new Date(start);
      const e = new Date(s.getTime() + Number(hours) * 3_600_000);
      return marketplace.addSlot(localInputToIso(start), e.toISOString());
    },
    onSuccess: () => { setStart(''); refresh(); },
  });
  const remove = useMutation({ mutationFn: marketplace.removeSlot, onSuccess: refresh });

  return (
    <Card>
      <SectionTitle icon={<CalendarClock size={20} className="text-plum" />} title="Availability"
        subtitle="Add dated time slots customers can book. You still confirm every booking yourself." />
      <form className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end" onSubmit={(e) => { e.preventDefault(); if (start) add.mutate(); }}>
        <Field label="Starts" htmlFor="slot-start"><Input id="slot-start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
        <Field label="Length" htmlFor="slot-hours">
          <Select id="slot-hours" value={hours} onChange={(e) => setHours(e.target.value)}>
            {['1', '2', '3', '4', '6', '8'].map((h) => <option key={h} value={h}>{h} h</option>)}
          </Select>
        </Field>
        <Button type="submit" disabled={!start || add.isPending}>{add.isPending ? 'Adding…' : 'Add slot'}</Button>
      </form>
      {add.isError && <div className="mt-3"><Alert kind="error">{errorMessage(add.error)}</Alert></div>}
      {remove.isError && <div className="mt-3"><Alert kind="error">{errorMessage(remove.error)}</Alert></div>}
      <ul className="mt-4 divide-y divide-ink/10">
        {slots.isLoading && <li className="py-3 text-sm text-ink/50">Loading slots…</li>}
        {slots.data?.length === 0 && <li className="py-3 text-sm text-ink/50">No upcoming slots yet.</li>}
        {slots.data?.map((s) => (
          <li key={s.id} className="flex items-center justify-between gap-3 py-3 text-sm">
            <span>{timeRange(s.starts_at, s.ends_at)}</span>
            <span className="flex items-center gap-2">
              {s.booking_status ? <StatusPill status={s.booking_status} /> : <span className="text-xs text-emerald-700">Free</span>}
              <button type="button" onClick={() => remove.mutate(s.id)} disabled={remove.isPending}
                className="rounded-full p-2 text-ink/50 hover:bg-rose-50 hover:text-rose-600" aria-label={`Remove slot ${timeRange(s.starts_at, s.ends_at)}`}>
                <Trash2 size={15} />
              </button>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function EarningsSection() {
  const earnings = useQuery({ queryKey: ['earnings'], queryFn: marketplace.earnings });
  if (earnings.isLoading) return null;
  if (earnings.isError) return <Alert kind="error">Could not load earnings: {errorMessage(earnings.error)}</Alert>;
  const e = earnings.data!;
  return (
    <Card>
      <SectionTitle icon={<Wallet size={20} className="text-plum" />} title="Earnings (simulated)" subtitle={e.fee_policy} />
      <SimulatedPaymentBanner label={e.label} />
      <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
        <div className="rounded-2xl bg-ink/5 p-3"><dt className="text-xs text-ink/60">Customer paid</dt><dd className="font-bold">{rupees(e.totals.gross_paise)}</dd></div>
        <div className="rounded-2xl bg-ink/5 p-3"><dt className="text-xs text-ink/60">Platform fee</dt><dd className="font-bold">{rupees(e.totals.fee_paise)}</dd></div>
        <div className="rounded-2xl bg-emerald-50 p-3"><dt className="text-xs text-emerald-700">Your payout</dt><dd className="font-bold text-emerald-800">{rupees(e.totals.payout_paise)}</dd></div>
      </dl>
      <p className="mt-2 text-xs text-ink/50">{e.totals.count} completed booking(s) · reconciles: {e.totals.reconciles ? 'yes' : 'NO'}</p>
    </Card>
  );
}
