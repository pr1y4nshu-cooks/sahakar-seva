import { ArrowRight, HandHeart, MapPin, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Card } from "../components/ui/Card";
import { publicApi } from "../lib/trust";

export function Home() {
  const overview = useQuery({ queryKey: ["overview"], queryFn: publicApi.overview, staleTime: 60_000, retry: false });
  const o = overview.data;
  return <div className="mx-auto max-w-6xl px-5 pb-10 pt-16 lg:px-8 lg:pt-24">
    <div className="max-w-3xl">
      <p className="mb-5 text-sm font-bold uppercase tracking-[0.2em] text-plum">Local work. Shared prosperity.</p>
      <h1 className="text-5xl font-black leading-[1.05] tracking-tight text-ink md:text-7xl">Trusted help, <span className="text-plum">close to home.</span></h1>
      <p className="mt-7 max-w-xl text-lg leading-8 text-ink/60">SAHAKAR–SEVA is building a fairer way to connect people with skilled local workers and meaningful opportunities.</p>
      <div className="mt-9 flex flex-col gap-3 sm:flex-row"><Link to="/hire" className="flex items-center justify-center gap-2 rounded-full bg-plum px-6 py-3.5 font-semibold text-white">Hire a Worker <ArrowRight size={17} /></Link><Link to="/find-work" className="rounded-full border border-ink/15 px-6 py-3.5 text-center font-semibold text-ink">Find Work</Link></div>
    </div>
    {o && (
      <section aria-label="Marketplace today" className="mt-12 max-w-3xl" data-testid="home-counts">
        <dl className="grid grid-cols-3 gap-3">
          <div className="rounded-2xl border border-[#e9e3f0] bg-white p-4"><dt className="text-xs text-ink/60">Workers available</dt><dd className="text-3xl font-black text-plum" data-testid="count-workers">{o.is_demo_dataset ? o.sample_data_share.workers : o.available_workers}</dd></div>
          <div className="rounded-2xl border border-[#e9e3f0] bg-white p-4"><dt className="text-xs text-ink/60">Service categories</dt><dd className="text-3xl font-black text-plum" data-testid="count-categories">{o.service_categories}</dd></div>
          <div className="rounded-2xl border border-[#e9e3f0] bg-white p-4"><dt className="text-xs text-ink/60">Open local jobs</dt><dd className="text-3xl font-black text-plum" data-testid="count-jobs">{o.is_demo_dataset ? o.sample_data_share.open_jobs : o.open_jobs}</dd></div>
        </dl>
        {o.is_demo_dataset && <p className="mt-2 text-xs font-semibold text-amber-800" data-testid="home-demo-label">{o.demo_label}. {o.note}</p>}
        {o.is_demo_dataset && <p className="text-[11px] text-ink/50" data-testid="home-db-total">This local database also holds {o.available_workers - o.sample_data_share.workers} older test worker profile(s) and {o.open_jobs - o.sample_data_share.open_jobs} older open job(s) from automated test runs; the figures above are the sample dataset only.</p>}
        {o.is_demo_dataset && <p className="mt-1 text-xs"><Link to="/demo" className="font-semibold text-plum underline">See the transaction transparency demo</Link> · <Link to="/pricing" className="font-semibold text-plum underline">How charges work</Link></p>}
      </section>
    )}
    <div className="mt-20 grid gap-4 md:grid-cols-3">
      {[["People-first by design", HandHeart, "One account can grow with your needs, whether you are hiring, working, or both."], ["Hyperlocal by nature", MapPin, "Future services will be shaped around real neighborhoods and practical distance."], ["Built on trust", ShieldCheck, "Clear policies and thoughtful verification are part of the foundation."]].map(([title, Icon, text]) => <Card key={title as string}><Icon className="mb-8 text-plum" size={25} /><h2 className="font-bold">{title as string}</h2><p className="mt-3 text-sm leading-6 text-ink/60">{text as string}</p></Card>)}
    </div>
  </div>;
}

