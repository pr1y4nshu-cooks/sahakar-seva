import { LayoutDashboard, Briefcase, Building2, User, Settings, Loader2, LogOut, ArrowRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useMyOrganizations, useWorkerProfile } from "@/hooks/useApi";
import { Card } from "@/components/ui/Card";
import { PageWrapper } from "@/components/ui/States";
import type { WorkerProfile, OrganizationWithMyRole } from "@/types/api";

export function Dashboard() {
  const navigate = useNavigate();
  const { user, session, loading: authLoading, signOut } = useAuth();
  const [workerProfile, setWorkerProfile] = useState<WorkerProfile | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationWithMyRole[]>([]);

  const { data: workerProfileData, isLoading: workerLoading } = useWorkerProfile({
    enabled: !!session?.access_token && !authLoading,
  });

  const { data: organizationsData = [], isLoading: orgLoading } = useMyOrganizations({
    enabled: !!session?.access_token && !authLoading,
  });

  // Sync state with hook data
  useEffect(() => {
    if (workerProfileData) setWorkerProfile(workerProfileData);
  }, [workerProfileData]);

  useEffect(() => {
    setOrganizations(organizationsData);
  }, [organizationsData]);

  const handleSignOut = async () => {
    await signOut();
    navigate("/");
  };

  const isLoading = authLoading || workerLoading || orgLoading;

  if (isLoading) {
    return (
      <PageWrapper
        isLoading
        loadingText="Loading dashboard..."
        className="min-h-screen bg-cream"
      >
        <div />
      </PageWrapper>
    );
  }

  if (!user) {
    return null;
  }

  const statusLabels: Record<string, { label: string; color: string; bg: string }> = {
    draft: { label: "Draft", color: "text-amber-700", bg: "bg-amber-50" },
    pending_review: { label: "Pending Review", color: "text-blue-700", bg: "bg-blue-50" },
    approved: { label: "Approved", color: "text-emerald-700", bg: "bg-emerald-50" },
    restricted: { label: "Restricted", color: "text-rose-700", bg: "bg-rose-50" },
  };

  const roleLabels: Record<string, { label: string; color: string; bg: string }> = {
    owner: { label: "Owner", color: "text-plum", bg: "bg-plum/10" },
    admin: { label: "Admin", color: "text-blue-700", bg: "bg-blue-50" },
    member: { label: "Member", color: "text-ink/60", bg: "bg-ink/5" },
  };

  return (
    <PageWrapper className="min-h-screen bg-cream py-12 px-4">
      <div className="mx-auto max-w-4xl">
        <div className="mb-8">
          <h1 className="text-3xl font-black text-ink">Dashboard</h1>
          <p className="mt-2 text-ink/60">Welcome back, {user.display_name || user.email?.split("@")[0] || "User"}!</p>
        </div>

        {/* Quick Stats */}
        <div className="grid gap-4 md:grid-cols-3 mb-8">
          <Card className="p-6 text-center bg-white border-plum/20">
            <User className="mx-auto h-10 w-10 text-plum" />
            <h3 className="mt-3 text-2xl font-bold text-ink">1</h3>
            <p className="text-sm text-ink/60">Account</p>
          </Card>
          <Card className="p-6 text-center bg-white">
            <Briefcase className="mx-auto h-10 w-10 text-ink/60" />
            <h3 className="mt-3 text-2xl font-bold text-ink">{workerProfile ? "1" : "0"}</h3>
            <p className="text-sm text-ink/60">Worker Profile</p>
            {workerProfile && (
              <span className={`mt-1 inline-block px-2 py-0.5 text-xs rounded-full ${statusLabels[workerProfile.onboarding_status].bg} ${statusLabels[workerProfile.onboarding_status].color}`}>
                {statusLabels[workerProfile.onboarding_status].label}
              </span>
            )}
          </Card>
          <Card className="p-6 text-center bg-white">
            <Building2 className="mx-auto h-10 w-10 text-ink/60" />
            <h3 className="mt-3 text-2xl font-bold text-ink">{organizations.length}</h3>
            <p className="text-sm text-ink/60">Organizations</p>
          </Card>
        </div>

        {/* Navigation Cards */}
        <div className="grid gap-4 md:grid-cols-2 mb-8">
          <Link to="/earn" className="block">
            <Card className="p-6 hover:border-plum/50 hover:bg-plum/5 transition-all group">
              <div className="flex items-start justify-between">
                <div>
                  <div className="h-12 w-12 rounded-xl bg-plum/10 flex items-center justify-center group-hover:bg-plum/20 transition-colors">
                    <Briefcase className="h-6 w-6 text-plum" />
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-ink">Earn — Worker Profile</h3>
                  <p className="mt-1 text-sm text-ink/60">
                    {workerProfile
                      ? `Status: ${statusLabels[workerProfile.onboarding_status].label}. Manage your profile and availability.`
                      : "Create your worker profile to offer services."}
                  </p>
                </div>
                <ArrowRight className="h-6 w-6 text-ink/40 group-hover:text-plum transition-colors" />
              </div>
            </Card>
          </Link>

          <Link to="/organizations" className="block">
            <Card className="p-6 hover:border-plum/50 hover:bg-plum/5 transition-all group">
              <div className="flex items-start justify-between">
                <div>
                  <div className="h-12 w-12 rounded-xl bg-ink/5 flex items-center justify-center group-hover:bg-ink/10 transition-colors">
                    <Building2 className="h-6 w-6 text-ink/60" />
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-ink">Organizations</h3>
                  <p className="mt-1 text-sm text-ink/60">
                    {organizations.length > 0
                      ? `You belong to ${organizations.length} organization(s). Manage members and post jobs.`
                      : "Create a business or cooperative to work as a team."}
                  </p>
                </div>
                <ArrowRight className="h-6 w-6 text-ink/40 group-hover:text-plum transition-colors" />
              </div>
            </Card>
          </Link>

          <Link to="/hire" className="block">
            <Card className="p-6 hover:border-plum/50 hover:bg-plum/5 transition-all group opacity-60 pointer-events-none">
              <div className="flex items-start justify-between">
                <div>
                  <div className="h-12 w-12 rounded-xl bg-ink/5 flex items-center justify-center">
                    <LayoutDashboard className="h-6 w-6 text-ink/40" />
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-ink/60">Hire — Find Workers</h3>
                  <p className="mt-1 text-sm text-ink/50">Coming in Phase 3: Discover and hire local workers.</p>
                </div>
                <span className="px-2 py-1 text-xs rounded-full bg-ink/5 text-ink/40">Soon</span>
              </div>
            </Card>
          </Link>

          <Link to="/find-work" className="block">
            <Card className="p-6 hover:border-plum/50 hover:bg-plum/5 transition-all group opacity-60 pointer-events-none">
              <div className="flex items-start justify-between">
                <div>
                  <div className="h-12 w-12 rounded-xl bg-ink/5 flex items-center justify-center">
                    <Briefcase className="h-6 w-6 text-ink/40" />
                  </div>
                  <h3 className="mt-4 text-lg font-bold text-ink/60">Find Work — Job Board</h3>
                  <p className="mt-1 text-sm text-ink/50">Coming in Phase 3: Browse and apply to local jobs.</p>
                </div>
                <span className="px-2 py-1 text-xs rounded-full bg-ink/5 text-ink/40">Soon</span>
              </div>
            </Card>
          </Link>
        </div>

        {/* Account Section */}
        <Card className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-ink flex items-center gap-2">
              <Settings className="h-5 w-5 text-plum" />
              Account
            </h2>
          </div>
          <div className="space-y-4">
            <Link to="/profile" className="flex items-center justify-between p-3 rounded-lg border border-ink/10 hover:bg-ink/5 transition-colors">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-plum/10 flex items-center justify-center">
                  <User className="h-5 w-5 text-plum" />
                </div>
                <div>
                  <p className="font-medium text-ink">My Profile</p>
                  <p className="text-sm text-ink/60">Update display name and view account info</p>
                </div>
              </div>
              <ArrowRight className="h-5 w-5 text-ink/40" />
            </Link>

            <button
              onClick={handleSignOut}
              className="flex items-center justify-between w-full p-3 rounded-lg border border-rose-100 hover:bg-rose-50 transition-colors text-rose-600"
            >
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-rose-50 flex items-center justify-center">
                  <LogOut className="h-5 w-5 text-rose-600" />
                </div>
                <div>
                  <p className="font-medium">Sign Out</p>
                  <p className="text-sm text-rose-500">End your current session</p>
                </div>
              </div>
            </button>
          </div>
        </Card>

        {/* Phase 2 Notice */}
        <Card className="bg-plum/5 border-plum/20">
          <div className="flex items-start gap-3">
            <div className="h-8 w-8 rounded-lg bg-plum/20 flex items-center justify-center flex-shrink-0">
              <Settings className="h-4 w-4 text-plum" />
            </div>
            <div>
              <h3 className="font-semibold text-plum">Phase 2 — Identity & Profiles</h3>
              <p className="mt-1 text-sm text-plum/80">
                This is the foundation phase. Marketplace features (hiring, job posts, bookings, payments)
                will be built in future phases. All authentication is handled by Supabase Auth.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </PageWrapper>
  );
}