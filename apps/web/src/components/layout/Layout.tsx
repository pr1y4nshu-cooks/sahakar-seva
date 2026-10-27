import { Link, NavLink, Outlet } from "react-router-dom";
import { ArrowUpRight, Menu, LogOut, User, Briefcase, Building2 } from "lucide-react";
import { useAuth } from "../../lib/auth";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

const publicLinks = [["/hire", "Hire"], ["/find-work", "Find Work"]];
const authLinks = [
  { to: "/earn", label: "Earn", Icon: Briefcase },
  { to: "/organizations", label: "Organizations", Icon: Building2 },
  { to: "/profile", label: "Profile", Icon: User },
];

export function Layout() {
  const { user, session, loading: authLoading, signOut } = useAuth();
  const apiQuery = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const dbQuery = useQuery({ queryKey: ["db-health"], queryFn: api.databaseHealth, retry: false });

  const handleSignOut = async () => {
    await signOut();
  };

  return (
    <div className="min-h-screen bg-cream">
      <header className="border-b border-[#eee8f2] bg-cream/90">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 lg:px-8">
          <Link to="/" className="text-lg font-black tracking-tight text-ink">SAHAKAR<span className="text-plum">–</span>SEVA</Link>
          <nav className="hidden items-center gap-7 md:flex">
            {publicLinks.map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => `text-sm font-medium ${isActive ? "text-plum" : "text-ink/60 hover:text-ink"}`}>
                {label}
              </NavLink>
            ))}
            {user && authLinks.map((link) => (
              <NavLink key={link.to} to={link.to} className={({ isActive }) => `flex items-center gap-1.5 text-sm font-medium ${isActive ? "text-plum" : "text-ink/60 hover:text-ink"}`}>
                <link.Icon size={14} />
                {link.label}
              </NavLink>
            ))}
            {user ? (
              <button
                onClick={handleSignOut}
                className="flex items-center gap-1.5 rounded-full border border-rose-200 text-rose-600 hover:bg-rose-50 px-4 py-2 text-sm font-semibold"
              >
                <LogOut size={14} />
                Sign Out
              </button>
            ) : (
              <>
                <Link to="/login" className="rounded-full border border-ink/10 px-4 py-2 text-sm font-semibold text-ink/60 hover:text-ink">Sign In</Link>
                <Link to="/signup" className="rounded-full bg-plum px-4 py-2 text-sm font-semibold text-white hover:bg-[#5931a8]">Sign Up</Link>
              </>
            )}
          </nav>
          <button className="rounded-full border border-ink/10 p-2 md:hidden" aria-label="Open navigation"><Menu size={18} /></button>
        </div>
      </header>
      <main><Outlet /></main>
      <footer className="mx-auto mt-20 flex max-w-6xl flex-col gap-3 border-t border-[#eee8f2] px-5 py-8 text-sm text-ink/50 md:flex-row md:items-center md:justify-between lg:px-8">
        <span>Built for fair, local opportunity.</span><span>Phase 2 foundation · <ArrowUpRight className="inline" size={14} /> Identity & Profiles</span>
      </footer>
      <div className="fixed bottom-4 right-4 hidden rounded-2xl border border-[#e9e3f0] bg-white p-3 text-xs shadow-lg sm:block">
        <div className="mb-1 font-semibold text-ink">Development status</div>
        <div className="flex gap-3 text-ink/60"><span title="Frontend application is running"><i className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />Frontend</span><span title={apiQuery.isError ? "Backend API unavailable" : "Backend API connected"}><i className={`mr-1 inline-block h-2 w-2 rounded-full ${apiQuery.isSuccess ? "bg-emerald-500" : "bg-rose-400"}`} />API</span><span title={dbQuery.isError ? "Database unavailable" : "Database connected"}><i className={`mr-1 inline-block h-2 w-2 rounded-full ${dbQuery.isSuccess ? "bg-emerald-500" : "bg-rose-400"}`} />PostgreSQL</span></div>
        {user && <div className="mt-2 flex items-center gap-2 text-xs text-plum"><User size={10} />Signed in as {user.email}</div>}
      </div>
    </div>
  );
}
