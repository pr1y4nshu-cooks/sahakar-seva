import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Briefcase, ChevronDown, ChevronUp, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState, Loading } from '@/components/ui/States';
import { errorMessage, marketplace, rupees, timeRange, type Job } from '@/lib/marketplace';
import { Alert, StatusPill } from '@/components/marketplace/common';

export function MyJobs() {
  const jobs = useQuery({ queryKey: ['my-jobs'], queryFn: marketplace.myJobs });
  return (
    <div className="min-h-screen bg-cream px-4 py-10 lg:px-8">
      <div className="mx-auto max-w-4xl space-y-4">
        <h1 className="text-3xl font-black text-ink">My Jobs</h1>
        <p className="text-ink/60">Jobs you posted, or posted for organizations you manage. Select an applicant to send them a booking request.</p>
        {jobs.isLoading && <Loading />}
        {jobs.isError && <Alert kind="error">{errorMessage(jobs.error)}</Alert>}
        {jobs.data?.length === 0 && (
          <Card><EmptyState icon={<Briefcase size={24} />} title="No jobs yet" action={{ label: 'Post a job', href: '/hire' }} /></Card>
        )}
        {jobs.data?.map((job) => <ManagedJob key={job.id} job={job} />)}
      </div>
    </div>
  );
}

function ManagedJob({ job }: { job: Job }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(job.status === 'open');
  const apps = useQuery({ queryKey: ['job-apps', job.id], queryFn: () => marketplace.jobApplications(job.id), enabled: open });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['my-jobs'] });
    qc.invalidateQueries({ queryKey: ['job-apps', job.id] });
  };
  const select = useMutation({ mutationFn: (appId: string) => marketplace.selectApplicant(job.id, appId), onSuccess: refresh });
  const cancel = useMutation({ mutationFn: () => marketplace.cancelJob(job.id), onSuccess: refresh });

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold text-ink">{job.title}</h2>
          <p className="text-sm text-ink/60">{job.skill.name} · {job.locality} · {timeRange(job.starts_at, job.ends_at)} · {rupees(job.budget_paise)}</p>
          {job.organization_name && <p className="text-xs text-ink/50">On behalf of {job.organization_name}</p>}
          <p className="text-xs text-ink/50">Private address: {job.address_details}</p>
        </div>
        <StatusPill status={job.status} />
      </div>
      {job.booking_id && <p className="text-sm">A booking exists for this job — see <Link to="/bookings" className="font-semibold text-plum underline">My Bookings</Link>.</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => setOpen(!open)} className="flex items-center gap-1 text-sm font-semibold text-plum">
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />} Applications ({job.application_count ?? 0})
        </button>
        {job.status === 'open' && (
          <Button variant="outline" className="ml-auto px-4 py-2" disabled={cancel.isPending}
            onClick={() => window.confirm('Cancel this job? Pending applicants will be notified as rejected.') && cancel.mutate()}>
            Cancel job
          </Button>
        )}
      </div>
      {(select.isError || cancel.isError) && <Alert kind="error">{errorMessage(select.error ?? cancel.error)}</Alert>}
      {select.isSuccess && <Alert kind="success">Booking request sent to {select.data.worker_display_name}. They must confirm it.</Alert>}
      {open && (
        <ul className="divide-y divide-ink/10">
          {apps.isLoading && <li className="py-2 text-sm text-ink/50">Loading applications…</li>}
          {apps.data?.length === 0 && <li className="py-2 text-sm text-ink/50">No applications yet.</li>}
          {apps.data?.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <div>
                <p className="font-semibold text-ink">{a.worker_display_name}</p>
                <p className="flex items-center gap-1 text-xs text-amber-800"><ShieldAlert size={12} />{a.worker_verification_label}</p>
                {a.worker_distance_km !== null && <p className="text-xs text-ink/50">{a.worker_distance_km} km from the job</p>}
                {a.message && <p className="mt-1 text-sm text-ink/70">“{a.message}”</p>}
              </div>
              <div className="flex items-center gap-2">
                <StatusPill status={a.status} />
                {job.status === 'open' && a.status === 'applied' && (
                  <Button className="px-4 py-2" disabled={select.isPending} onClick={() => select.mutate(a.id)}>Select</Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
