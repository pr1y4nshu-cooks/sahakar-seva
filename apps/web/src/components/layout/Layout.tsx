import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { marketplace } from "@/lib/marketplace";
import { api } from "@/lib/api-adapter";
import { Menu, X, LogOut, User, Briefcase, Building2, CalendarCheck, ClipboardList, ListChecks, Scale } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { DevBadge } from "@/components/ui/DevBadge";
import { DemoGuide } from "@/components/trust/DemoGuide";
import { publicApi } from "@/lib/trust";

const publicLinks = [["/hire", "Hire"], ["/find-work", "Find Work"], ["/pricing", "Pricing"]];
const authLinks = [
  { to: "/bookings", label: "Bookings", Icon: CalendarCheck },
  { to: "/my-jobs", label: "My Jobs", Icon: ListChecks },
  { to: "/applications", label: "Applications", Icon: ClipboardList },
  { to: "/earn", label: "Earn", Icon: Briefcase },
  { to: "/organizations", label: "Organizations", Icon: Building2 },
  { to: "/profile", label: "Profile", Icon: User },
];

export function Layout() {
  const { user, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);
  const reviewer = useQuery({
    queryKey: ["reviewer-status", user?.id],
    queryFn: marketplace.reviewerStatus,
    enabled: !!user && !api.isFixturesMode(),
    staleTime: 300_000,
  });
  const overview = useQuery({ queryKey: ["overview"], queryFn: publicApi.overview, staleTime: 60_000, retry: false, enabled: !api.isFixturesMode() });
  const links = [
    ...authLinks,
    ...(reviewer.data?.is_dispute_reviewer ? [{ to: "/disputes/review", label: "Review", Icon: Scale }] : []),
  ];
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-1.5 text-sm font-medium ${isActive ? "text-plum" : "text-ink/60 hover:text-ink"}`;

  const navItems = (
    <>
      {publicLinks.map(([to, label]) => (
        <NavLink key={to} to={to} className={linkClass}>{label}</NavLink>
      ))}
      {user && links.map((link) => (
        <NavLink key={link.to} to={link.to} className={linkClass}>
          <link.Icon size={14} aria-hidden="true" />
          {link.label}
        </NavLink>
      ))}
      {user ? (
        <button
          onClick={() => signOut()}
          className="flex items-center gap-1.5 rounded-full border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-600 hover:bg-rose-50"
        >
          <LogOut size={14} aria-hidden="true" />
          Sign Out
        </button>
      ) : (
        <>
          <Link to="/login" className="rounded-full border border-ink/10 px-4 py-2 text-sm font-semibold text-ink/60 hover:text-ink">Sign In</Link>
          <Link to="/signup" className="rounded-full bg-plum px-4 py-2 text-sm font-semibold text-white hover:bg-[#5931a8]">Sign Up</Link>
        </>
      )}
    </>
  );

  return (
    <div className="min-h-screen bg-cream">
      {overview.data?.is_demo_dataset && (
        <div role="note" data-testid="demo-banner" className="bg-amber-100 px-4 py-1.5 text-center text-xs font-semibold text-amber-900">
          {overview.data.demo_label} · people, jobs and bookings are synthetic · payments are simulated
        </div>
      )}
      <header className="border-b border-[#eee8f2] bg-cream/90">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 lg:px-8">
          <Link to="/" className="text-lg font-black tracking-tight text-ink">SAHAKAR<span className="text-plum">–</span>SEVA</Link>
          <nav className="hidden items-center gap-5 lg:flex" aria-label="Main">{navItems}</nav>
          <button
            className="rounded-full border border-ink/10 p-2 lg:hidden"
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            onClick={() => setMenuOpen((v) => !v)}
          >
            {menuOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
        {menuOpen && (
          <nav id="mobile-nav" aria-label="Main" className="flex flex-col items-start gap-4 border-t border-[#eee8f2] px-5 py-4 lg:hidden">
            {navItems}
          </nav>
        )}
      </header>
      <main><Outlet /></main>
      <footer className="mx-auto mt-20 flex max-w-6xl flex-col gap-3 border-t border-[#eee8f2] px-5 py-8 text-sm text-ink/50 md:flex-row md:items-center md:justify-between lg:px-8">
        <span>Built for fair, local opportunity.</span>
        <span>Hackathon MVP · payments are simulated, no real money moves</span>
      </footer>
      <DevBadge />
      <DemoGuide />
    </div>
  );
}
