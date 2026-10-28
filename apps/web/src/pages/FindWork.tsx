import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Briefcase, Clock, MapPin } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { EmptyState, Loading } from '@/components/ui/States';
import { errorMessage, marketplace, rupees, timeRange, type Job } from '@/lib/marketplace';
import { publicApi, type OpenJob } from '@/lib/trust';
import { Alert, Field, Select, StatusPill } from '@/components/marketplace/common';

export function FindWork() {
  const { user, loading } = useAuth();
  const [skillId, setSkillId] = useState('');
  const skills = useQuery({ queryKey: ['skills', 'all'], queryFn: () => marketplace.skills(), staleTime: 300_000 });
  const jobs = useQuery({
    queryKey: ['nearby-jobs', skillId],
    queryFn: () => marketplace.nearbyJobs(skillId || undefined),
    enabled: !!user,
    retry: false,
  });

  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <p className="mb-3 text-sm font-bold uppercase tracking-[0.2em] text-plum">Find local work</p>
        <h1 className="text-3xl font-black tracking-tight text-ink lg:text-4xl">Jobs within your service area</h1>
        <p className="mt-2 max-w-2xl text-ink/60">Open jobs inside your service radius, with the budget shown up front. You choose what to apply for, and you confirm any booking yourself.</p>

        {loading ? <Loading /> : !user ? (
          <PublicBoard />
        ) : (
          <>
            <div className="mt-6 max-w-sm">
              <Field label="Filter by skill" htmlFor="fw-skill">
                <Select id="fw-skill" value={skillId} onChange={(e) => setSkillId(e.target.value)}>
                  <option value="">All skills</option>
                  {skills.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </Select>
              </Field>
            </div>
            <div className="mt-6">
              {jobs.isLoading && <Loading text="Finding nearby jobs…" />}
              {jobs.isError && (
                <Card>
                  <Alert kind="info">{errorMessage(jobs.error)}</Alert>
                  <Link to="/earn" className="mt-3 inline-block text-sm font-semibold text-plum underline">Set up your worker profile on the Earn page</Link>
                </Card>
              )}
              {jobs.data && jobs.data.length === 0 && (
                <Card><EmptyState icon={<Briefcase size={24} />} title="No open jobs in your area right now"
                  description="New jobs within your service radius will appear here. Increasing your radius on the Earn page shows more." /></Card>
              )}
              <div className="grid gap-4 md:grid-cols-2">
                {jobs.data?.map((job) => <JobCard key={job.id} job={job} />)}
              </div>
            </div>
            <p className="mt-6 text-sm text-ink/60">Track what you applied for in <Link to="/applications" className="font-semibold text-plum underline">My Applications</Link>.</p>
          </>
        )}
      </div>
    </div>
  );
}

function JobCard({ job }: { job: Job }) {
  const qc = useQueryClient();
  const [message, setMessage] = useState('');
  const apply = useMutation({
    mutationFn: () => marketplace.apply(job.id, message),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['nearby-jobs'] }),
  });
  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <span className="rounded-full bg-plum/10 px-2 py-1 text-xs font-medium text-plum">{job.skill.name}</span>
        {job.my_application_status && <StatusPill status={job.my_application_status} />}
      </div>
      <h3 className="text-lg font-bold text-ink">{job.title}</h3>
      <p className="text-sm text-ink/70">{job.description}</p>
      <p className="flex items-center gap-1 text-sm text-ink/60"><MapPin size={14} aria-hidden="true" />{job.locality}{job.distance_km !== null ? ` · ${job.distance_km} km from your service centre` : ''}</p>
      <p className="flex items-center gap-1 text-sm text-ink/60"><Clock size={14} aria-hidden="true" />{timeRange(job.starts_at, job.ends_at)}</p>
      <p className="text-lg font-bold text-plum">{rupees(job.budget_paise)} <span className="text-xs font-normal text-ink/50">total budget</span></p>
      {job.organization_name && <p className="text-xs text-ink/50">Posted for {job.organization_name}</p>}
      {!job.my_application_status && (
        job.i_declared_skill ? (
          <form className="space-y-2 border-t border-ink/10 pt-3" onSubmit={(e) => { e.preventDefault(); apply.mutate(); }}>
            <Field label="Message to the customer (optional)" htmlFor={`msg-${job.id}`}>
              <Input id={`msg-${job.id}`} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={500} />
            </Field>
            {apply.isError && <Alert kind="error">{errorMessage(apply.error)}</Alert>}
            <Button type="submit" className="w-full" disabled={apply.isPending}>{apply.isPending ? 'Applying…' : 'Apply'}</Button>
          </form>
        ) : (
          <Alert kind="info">Declare “{job.skill.name}” on your <Link to="/earn" className="underline">Earn page</Link> to apply.</Alert>
        )
      )}
      {apply.isSuccess && <Alert kind="success">Applied. The customer will review applicants.</Alert>}
    </Card>
  );
}

/** Visitors can browse open jobs without an account. Applying needs a worker profile (server-enforced). */
function PublicBoard() {
  const [skillId, setSkillId] = useState('');
  const skills = useQuery({ queryKey: ['skills', 'all'], queryFn: () => marketplace.skills(), staleTime: 300_000 });
  const overview = useQuery({ queryKey: ['overview'], queryFn: publicApi.overview, staleTime: 60_000, retry: false });
  const [sampleOnly, setSampleOnly] = useState(true);
  const sample = !!overview.data?.is_demo_dataset && sampleOnly;
  const jobs = useQuery({ queryKey: ['open-jobs', skillId, sample], queryFn: () => publicApi.openJobs(skillId || undefined, sample), retry: false, enabled: !overview.isLoading });  // wait for the overview so the board never flashes an unfiltered list
  return (
    <div className="mt-6" data-testid="public-job-board">
      <Alert kind="info">Browsing as a visitor. <Link to="/login" className="font-semibold underline">Sign in</Link> as a worker to apply; nearby matching uses your service area.</Alert>
      <div className="mt-4 max-w-sm">
        <Field label="Filter by skill" htmlFor="pj-skill">
          <Select id="pj-skill" value={skillId} onChange={(e) => setSkillId(e.target.value)}>
            <option value="">All skills</option>{skills.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
      </div>
      {overview.data?.is_demo_dataset && (
        <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={sampleOnly} onChange={(e) => setSampleOnly(e.target.checked)} />Sample dataset only</label>
      )}
      <div className="mt-4">
        {jobs.isLoading && <Loading text="Loading open jobs…" />}
        {jobs.isError && <Alert kind="error">{errorMessage(jobs.error)}</Alert>}
        {jobs.data?.length === 0 && <Card><EmptyState icon={<Briefcase size={24} />} title="No open jobs right now" description="New jobs appear here as customers post them." /></Card>}
        <div className="grid gap-4 md:grid-cols-2">
          {jobs.data?.map((j: OpenJob) => (
            <Card key={j.id} className="space-y-2" data-testid="public-job-card">
              <div className="flex items-start justify-between gap-2">
                <span className="rounded-full bg-plum/10 px-2 py-1 text-xs font-medium text-plum">{j.skill.name}</span>
                {j.is_synthetic_demo && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900">Sample job</span>}
              </div>
              <h3 className="text-lg font-bold text-ink">{j.title}</h3>
              <p className="text-sm text-ink/70">{j.description}</p>
              <p className="flex items-center gap-1 text-sm text-ink/60"><MapPin size={14} aria-hidden="true" />{j.locality}</p>
              <p className="flex items-center gap-1 text-sm text-ink/60"><Clock size={14} aria-hidden="true" />{timeRange(j.starts_at, j.ends_at)}</p>
              <p className="text-lg font-bold text-plum">{rupees(j.budget_paise)} <span className="text-xs font-normal text-ink/50">total budget</span></p>
              {j.organization_name && <p className="text-xs text-ink/50">Posted for {j.organization_name}</p>}
              <Link to="/login" className="inline-block rounded-full border border-plum px-4 py-1.5 text-sm font-semibold text-plum">Sign in to apply</Link>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
