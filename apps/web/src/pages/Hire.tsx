import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Briefcase, Clock, Loader2, MapPin, Search, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { useMyOrganizations } from '@/hooks/useApi';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { EmptyState } from '@/components/ui/States';
import { errorMessage, marketplace, RADII, rupees, timeRange, type WorkerResult } from '@/lib/marketplace';
import { Alert, Field, LocationPicker, PickedLocation, Select, TextArea, localInputToIso } from '@/components/marketplace/common';
import { ProtectedBookingBenefits } from '@/components/trust/TrustPanel';
import { BEARER_LABELS, publicApi, trust } from '@/lib/trust';

function useTaxonomy(categoryId: string) {
  const categories = useQuery({ queryKey: ['categories'], queryFn: marketplace.categories, staleTime: 300_000 });
  const skills = useQuery({
    queryKey: ['skills', categoryId],
    queryFn: () => marketplace.skills(categoryId),
    enabled: !!categoryId,
    staleTime: 300_000,
  });
  return { categories, skills };
}

export function Hire() {
  const [params] = useSearchParams();
  const template = params.get('template');
  const [tab, setTab] = useState<'find' | 'post'>(template ? 'post' : 'find');
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <p className="mb-3 text-sm font-bold uppercase tracking-[0.2em] text-plum">Hire local help</p>
        <h1 className="text-3xl font-black tracking-tight text-ink lg:text-4xl">Hire a nearby worker</h1>
        <p className="mt-2 max-w-2xl text-ink/60">
          Search workers who serve your area and book a free slot, or post a job and choose from applicants.
          Skills are self-declared unless marked as platform approved.
        </p>
        <div role="tablist" aria-label="Hiring method" className="mt-6 inline-flex rounded-full border border-ink/10 bg-white p-1">
          {([['find', 'Find a worker'], ['post', 'Post a job']] as const).map(([key, label]) => (
            <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
              className={`rounded-full px-5 py-2 text-sm font-semibold ${tab === key ? 'bg-plum text-white' : 'text-ink/60 hover:text-ink'}`}>
              {label}
            </button>
          ))}
        </div>
        <div className="mt-6">{tab === 'find' ? <FindWorker /> : <PostJob templateJobId={template} />}</div>
      </div>
    </div>
  );
}

function FindWorker() {
  const [categoryId, setCategoryId] = useState('');
  const [skillId, setSkillId] = useState('');
  const [location, setLocation] = useState<PickedLocation | null>(null);
  const [radius, setRadius] = useState(5);
  const overview = useQuery({ queryKey: ['overview'], queryFn: publicApi.overview, staleTime: 60_000, retry: false });
  const localities = useQuery({ queryKey: ['localities'], queryFn: marketplace.localities, staleTime: Infinity });
  const [sampleOnly, setSampleOnly] = useState(true);
  const [when, setWhen] = useState('');
  const [hours, setHours] = useState('2');
  const { categories, skills } = useTaxonomy(categoryId);

  // Demo convenience: with a sample dataset present, start in its default locality and show matching workers at once.
  const defaultLocality = overview.data?.default_locality;
  const autoRan = useRef(false);
  useEffect(() => {
    if (!defaultLocality || location || !localities.data) return;
    const l = localities.data.find((x) => x.name === defaultLocality);
    if (l) setLocation({ locality: l.name, latitude: l.latitude, longitude: l.longitude });
  }, [defaultLocality, localities.data, location]);
  useEffect(() => {  // the API requires a service category or skill, so the demo starts on the first category
    if (defaultLocality && !categoryId && categories.data?.length) setCategoryId(categories.data[0].id);
  }, [defaultLocality, categories.data, categoryId]);

  const search = useMutation({
    mutationFn: () => {
      const starts = when ? new Date(when) : null;
      return marketplace.searchWorkers({
        latitude: location!.latitude,
        longitude: location!.longitude,
        radius_km: radius,
        category_id: skillId ? undefined : categoryId,
        skill_id: skillId || undefined,
        sample_only: !!overview.data?.is_demo_dataset && sampleOnly,
        starts_at: starts ? starts.toISOString() : undefined,
        ends_at: starts ? new Date(starts.getTime() + Number(hours) * 3_600_000).toISOString() : undefined,
      });
    },
  });

  useEffect(() => {
    if (location && categoryId && defaultLocality && !autoRan.current && !search.isPending) { autoRan.current = true; search.mutate(); }
  }, [location, categoryId, defaultLocality]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">
      <Card>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (categoryId && location) search.mutate(); }}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Service" htmlFor="h-cat">
              <Select id="h-cat" value={categoryId} onChange={(e) => { setCategoryId(e.target.value); setSkillId(''); }} required>
                <option value="">Choose a service…</option>
                {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </Field>
            <Field label="Specific skill (optional)" htmlFor="h-skill">
              <Select id="h-skill" value={skillId} onChange={(e) => setSkillId(e.target.value)} disabled={!categoryId}>
                <option value="">Any skill in this service</option>
                {skills.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </Field>
          </div>
          <Field label="Where is the job?" htmlFor="h-loc"><LocationPicker id="h-loc" value={location} onChange={setLocation} /></Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Search radius" htmlFor="h-radius">
              <Select id="h-radius" value={radius} onChange={(e) => setRadius(Number(e.target.value))}>
                {RADII.map((r) => <option key={r} value={r}>Within {r} km</option>)}
              </Select>
            </Field>
            <Field label="Date and time (optional)" htmlFor="h-when"><Input id="h-when" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
            <Field label="Duration" htmlFor="h-hours">
              <Select id="h-hours" value={hours} onChange={(e) => setHours(e.target.value)} disabled={!when}>
                {['1', '2', '3', '4'].map((h) => <option key={h} value={h}>{h} h</option>)}
              </Select>
            </Field>
          </div>
          {overview.data?.is_demo_dataset && (
            <label className="flex items-center gap-2 text-sm" data-testid="sample-only"><input type="checkbox" checked={sampleOnly} onChange={(e) => setSampleOnly(e.target.checked)} />Sample dataset only <span className="text-xs text-ink/50">(untick to include older test profiles in this local database)</span></label>
          )}
          <Button type="submit" disabled={!categoryId || !location || search.isPending} className="gap-2">
            {search.isPending ? <Loader2 className="inline h-4 w-4 animate-spin" /> : <Search className="inline" size={16} />} Search workers
          </Button>
        </form>
      </Card>

      {search.isError && <Alert kind="error">{errorMessage(search.error)}</Alert>}
      {search.data && (
        <section aria-live="polite">
          <h2 className="mb-1 text-xl font-bold text-ink">{search.data.total} matching worker{search.data.total === 1 ? '' : 's'}</h2>
          <p className="mb-4 text-xs text-ink/50">Matched on declared skill, service radius covering your location, your search radius{when ? ', and a free slot at your time' : ''}. Ordered by distance.</p>
          {search.data.total === 0 ? (
            <Card><EmptyState icon={<Search size={24} />} title="No eligible workers found"
              description="Nobody currently serves this location with that skill. Try a larger radius, another time, or post a job instead." /></Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {search.data.results.map((w) => <WorkerCard key={w.worker_profile_id} worker={w} location={location!} skillId={skillId} />)}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function WorkerCard({ worker, location, skillId }: { worker: WorkerResult; location: PickedLocation; skillId: string }) {
  const { user } = useAuth();
  const [slotId, setSlotId] = useState<string | null>(null);
  const [skill, setSkill] = useState(skillId || worker.skills[0]?.id || '');
  const [address, setAddress] = useState('');
  const [notes, setNotes] = useState('');
  const book = useMutation({
    mutationFn: () => marketplace.requestBooking({
      worker_profile_id: worker.worker_profile_id, slot_id: slotId!, skill_id: skill,
      locality: location.locality, latitude: location.latitude, longitude: location.longitude,
      address_details: address, customer_notes: notes || undefined,
    }),
  });
  const approved = worker.onboarding_status === 'approved';
  const chosen = worker.available_slots.find((s) => s.id === slotId);

  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold text-ink">{worker.display_name}</h3>
          <p className="flex items-center gap-1 text-sm text-ink/60"><MapPin size={14} aria-hidden="true" />{worker.locality} · {worker.distance_km} km away · serves {worker.service_radius_km} km</p>
        </div>
        <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${approved ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-800'}`}>
          {approved ? <ShieldCheck size={13} /> : <ShieldAlert size={13} />}{worker.verification_label}
        </span>
      </div>
      {worker.bio && <p className="text-sm text-ink/70">{worker.bio}</p>}
      <div className="flex flex-wrap gap-1.5">
        {worker.skills.map((s) => <span key={s.id} className="rounded bg-plum/10 px-2 py-1 text-xs text-plum">{s.name}</span>)}
        <span className="px-1 py-1 text-xs text-ink/50">Self-declared skills</span>
      </div>
      <p className="text-sm font-semibold text-ink">{rupees(worker.hourly_rate_paise)}/hour</p>
      <ul className="list-disc pl-5 text-xs text-ink/50">{worker.match_reasons.map((r) => <li key={r}>{r}</li>)}</ul>

      <div>
        <p className="mb-2 flex items-center gap-1 text-sm font-medium text-ink"><Clock size={14} aria-hidden="true" />Free slots</p>
        {worker.available_slots.length === 0 ? (
          <p className="text-sm text-ink/50">No free slots right now.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {worker.available_slots.map((s) => (
              <button key={s.id} type="button" aria-pressed={slotId === s.id} onClick={() => setSlotId(s.id)}
                className={`rounded-xl border px-3 py-2 text-left text-xs ${slotId === s.id ? 'border-plum bg-plum/10' : 'border-ink/15 hover:bg-ink/5'}`}>
                {timeRange(s.starts_at, s.ends_at)}<br /><span className="font-semibold">{rupees(s.price_paise)}</span> <span className="text-ink/50">service</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {slotId && !user && (
        <Alert kind="info"><Link to="/login" className="font-semibold underline">Sign in</Link> to request this booking.</Alert>
      )}
      {slotId && user && !book.isSuccess && (
        <form className="space-y-3 border-t border-ink/10 pt-3" onSubmit={(e) => { e.preventDefault(); book.mutate(); }}>
          <Field label="Skill needed" htmlFor={`bk-skill-${worker.worker_profile_id}`}>
            <Select id={`bk-skill-${worker.worker_profile_id}`} value={skill} onChange={(e) => setSkill(e.target.value)}>
              {worker.skills.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Exact address (shared only after the worker accepts)" htmlFor={`bk-addr-${worker.worker_profile_id}`}>
            <TextArea id={`bk-addr-${worker.worker_profile_id}`} value={address} onChange={(e) => setAddress(e.target.value)} minLength={5} maxLength={500} required />
          </Field>
          <Field label="Notes for the worker (optional)" htmlFor={`bk-notes-${worker.worker_profile_id}`}>
            <Input id={`bk-notes-${worker.worker_profile_id}`} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} />
          </Field>
          {chosen && <BookingPreview worker={worker} slot={chosen} />}
          {book.isError && <Alert kind="error">{errorMessage(book.error)}</Alert>}
          <Button type="submit" disabled={address.trim().length < 5 || book.isPending} className="w-full">
            {book.isPending ? 'Sending request…' : 'Request booking'}
          </Button>
        </form>
      )}
      {book.isSuccess && (
        <Alert kind="success">Booking requested. The worker must accept it. Track it in <Link to="/bookings" className="font-semibold underline">My Bookings</Link>.</Alert>
      )}
    </Card>
  );
}

/** Shown before the customer sends a request: the server prices the slot with the ACTIVE fee policy. */
function BookingPreview({ worker, slot }: { worker: WorkerResult; slot: WorkerResult['available_slots'][number] }) {
  const preview = useQuery({ queryKey: ['pricing-preview', slot.price_paise], queryFn: () => trust.preview(slot.price_paise), retry: false });
  const policy = useQuery({ queryKey: ['fee-policy'], queryFn: trust.feePolicy, staleTime: 60_000 });
  const minutes = Math.round((new Date(slot.ends_at).getTime() - new Date(slot.starts_at).getTime()) / 60000);
  const ev = preview.data?.evaluation;
  return (
    <div className="space-y-2 rounded-2xl bg-ink/5 p-3 text-sm" aria-label="Price before you confirm">
      <p className="font-semibold">Before you confirm</p>
      <p className="text-xs text-ink/60">{timeRange(slot.starts_at, slot.ends_at)} · {minutes / 60} h at {rupees(worker.hourly_rate_paise)}/hour</p>
      {preview.isError && <Alert kind="error">{errorMessage(preview.error)}</Alert>}
      {ev && (
        <dl className="space-y-0.5">
          <div className="flex justify-between"><dt>Service price</dt><dd className="font-bold">{rupees(ev.service_price_paise)}</dd></div>
          {ev.lines.map((l) => (
            <div key={l.code} className="flex justify-between pl-3 text-xs text-ink/70">
              <dt>{l.label} ({BEARER_LABELS[l.bearer]}){l.waived_by ? ` — waived (${l.waived_by})` : ''}</dt><dd>{rupees(l.amount_paise)}</dd>
            </div>
          ))}
          <div className="flex justify-between border-t border-ink/10 pt-1"><dt>Customer total (you pay)</dt><dd className="font-bold">{rupees(ev.customer_total_paise)}</dd></div>
          <div className="flex justify-between"><dt>Worker payout</dt><dd className="font-bold">{rupees(ev.worker_payout_paise)}</dd></div>
          <div className="flex justify-between"><dt>Platform charges</dt><dd className="font-bold">{rupees(ev.platform_fee_paise)}</dd></div>
          <div className="flex justify-between text-ink/60"><dt>Processing charges (modeled)</dt><dd>{ev.processing_charge_paise ? rupees(ev.processing_charge_paise) : 'None'}</dd></div>
          <div className="flex justify-between text-ink/60"><dt>Taxes</dt><dd>Not modeled</dd></div>
        </dl>
      )}
      {preview.data && (
        <p className="text-xs text-ink/60" data-testid="preview-policy">
          Fee policy {preview.data.policy.policy_id} v{preview.data.policy.version}{preview.data.policy.is_example ? ' — illustrative example, not final pricing' : ''}.
        </p>
      )}
      <p className="text-xs text-ink/60">Sending the request records quote version 1 with your acceptance. The worker accepts the same version when they accept the booking. A changed price needs a new version and both acceptances.</p>
      <p className="text-xs text-ink/60">Cancellation: you can cancel before the work starts; the worker can cancel a confirmed booking. Cancelled bookings record no charges. {policy.data?.rules.payments_note}</p>
      <ProtectedBookingBenefits compact />
    </div>
  );
}

function PostJob({ templateJobId }: { templateJobId?: string | null }) {
  const { user } = useAuth();
  const orgs = useMyOrganizations({ enabled: !!user });
  const [categoryId, setCategoryId] = useState('');
  const [skillId, setSkillId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState<PickedLocation | null>(null);
  const [address, setAddress] = useState('');
  const [start, setStart] = useState('');
  const [duration, setDuration] = useState('120');
  const [budget, setBudget] = useState('');
  const [orgId, setOrgId] = useState('');
  const { categories, skills } = useTaxonomy(categoryId);
  const template = useQuery({ queryKey: ['job', templateJobId], queryFn: () => marketplace.job(templateJobId!), enabled: !!templateJobId && !!user });
  const localities = useQuery({ queryKey: ['localities'], queryFn: marketplace.localities, staleTime: Infinity, enabled: !!templateJobId });
  useEffect(() => {
    const t = template.data;
    if (!t) return;
    setCategoryId(t.skill.category_id);
    setSkillId(t.skill.id);
    setTitle(t.title);
    setDescription(t.description);
    setAddress(t.address_details ?? '');
    setDuration(String(Math.round((new Date(t.ends_at).getTime() - new Date(t.starts_at).getTime()) / 60000)));
    setBudget(String(t.budget_paise / 100));
    setOrgId(t.organization_id ?? '');
    const loc = localities.data?.find((l) => l.name === t.locality);
    if (loc) setLocation({ locality: loc.name, latitude: loc.latitude, longitude: loc.longitude });
  }, [template.data, localities.data]);
  const post = useMutation({
    mutationFn: () => marketplace.postJob({
      skill_id: skillId, title, description, locality: location!.locality, latitude: location!.latitude,
      longitude: location!.longitude, address_details: address, starts_at: localInputToIso(start),
      duration_minutes: Number(duration), budget_paise: Math.round(Number(budget) * 100), organization_id: orgId || undefined,
    }),
  });

  if (!user) {
    return <Card><EmptyState icon={<Briefcase size={24} />} title="Sign in to post a job" description="Jobs are posted from your account so you can review applicants." action={{ label: 'Sign in', href: '/login' }} /></Card>;
  }
  if (post.isSuccess) {
    return <Alert kind="success">Job “{post.data.title}” is live for nearby workers with that skill. Review applicants in <Link to="/my-jobs" className="font-semibold underline">My Jobs</Link>.</Alert>;
  }
  const managedOrgs = (orgs.data ?? []).filter((o) => o.my_membership_role === 'owner' || o.my_membership_role === 'admin');
  const valid = skillId && title.trim().length >= 5 && description.trim().length >= 10 && location && address.trim().length >= 5 && start && Number(budget) >= 50;

  return (
    <Card>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (valid) post.mutate(); }}>
        {template.data && <Alert kind="info">Prefilled from “{template.data.title}”. Review every field and choose a new start time before publishing. Nothing is posted until you press Publish.</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Service" htmlFor="j-cat">
            <Select id="j-cat" value={categoryId} onChange={(e) => { setCategoryId(e.target.value); setSkillId(''); }} required>
              <option value="">Choose a service…</option>
              {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <Field label="Skill required" htmlFor="j-skill">
            <Select id="j-skill" value={skillId} onChange={(e) => setSkillId(e.target.value)} disabled={!categoryId} required>
              <option value="">Choose a skill…</option>
              {skills.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Title" htmlFor="j-title"><Input id="j-title" value={title} onChange={(e) => setTitle(e.target.value)} minLength={5} maxLength={120} required /></Field>
        <Field label="What needs doing?" htmlFor="j-desc"><TextArea id="j-desc" value={description} onChange={(e) => setDescription(e.target.value)} minLength={10} maxLength={2000} required /></Field>
        <Field label="Locality (shown publicly)" htmlFor="j-loc"><LocationPicker id="j-loc" value={location} onChange={setLocation} /></Field>
        <Field label="Exact address (private — shown only to the confirmed worker)" htmlFor="j-addr"><TextArea id="j-addr" value={address} onChange={(e) => setAddress(e.target.value)} required /></Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Starts" htmlFor="j-start"><Input id="j-start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
          <Field label="Duration" htmlFor="j-dur">
            <Select id="j-dur" value={duration} onChange={(e) => setDuration(e.target.value)}>
              {[60, 120, 180, 240, 360].map((m) => <option key={m} value={m}>{m / 60} h</option>)}
            </Select>
          </Field>
          <Field label="Budget (₹, total)" htmlFor="j-budget" hint="Agreed price if a worker is booked.">
            <Input id="j-budget" type="number" min={50} max={100000} value={budget} onChange={(e) => setBudget(e.target.value)} required />
          </Field>
        </div>
        {managedOrgs.length > 0 && (
          <Field label="Post on behalf of" htmlFor="j-org">
            <Select id="j-org" value={orgId} onChange={(e) => setOrgId(e.target.value)}>
              <option value="">Myself</option>
              {managedOrgs.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.organization_type})</option>)}
            </Select>
          </Field>
        )}
        {post.isError && <Alert kind="error">{errorMessage(post.error)}</Alert>}
        <Button type="submit" disabled={!valid || post.isPending}>{post.isPending ? 'Publishing…' : 'Publish job'}</Button>
      </form>
    </Card>
  );
}
