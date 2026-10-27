import { Briefcase, Loader2, Save, AlertCircle, CheckCircle, Info } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { useWorkerProfile, useCreateWorkerProfile, useUpdateWorkerProfile } from "@/hooks/useApi";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageWrapper, EmptyState, ErrorState } from "@/components/ui/States";

type OnboardingStatus = 'draft' | 'pending_review' | 'approved' | 'restricted';

const statusInfo: Record<OnboardingStatus, { label: string; color: string; bg: string; description: string }> = {
  draft: {
    label: "Draft",
    color: "text-amber-700",
    bg: "bg-amber-50 border-amber-200",
    description: "Your profile is a draft. It is not visible to customers yet. Complete your profile and submit for review when ready."
  },
  pending_review: {
    label: "Pending Review",
    color: "text-blue-700",
    bg: "bg-blue-50 border-blue-200",
    description: "Your profile is under review. You'll be notified once it's approved."
  },
  approved: {
    label: "Approved",
    color: "text-emerald-700",
    bg: "bg-emerald-50 border-emerald-200",
    description: "Your profile is approved and visible to customers looking for workers."
  },
  restricted: {
    label: "Restricted",
    color: "text-rose-700",
    bg: "bg-rose-50 border-rose-200",
    description: "Your profile has been restricted. Contact support for more information."
  },
};

export function Earn() {
  const navigate = useNavigate();
  const { session, loading: authLoading } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");

  const { data: profile, isLoading, error, refetch, isError } = useWorkerProfile({
    enabled: !!session?.access_token && !authLoading,
  });

  const createMutation = useCreateWorkerProfile();
  const updateMutation = useUpdateWorkerProfile();

  // Sync form state with profile data
  useEffect(() => {
    if (profile) {
      setDisplayName(profile.display_name);
      setBio(profile.bio ?? "");
    }
  }, [profile]);

  const handleCreate = async () => {
    if (!displayName.trim() || createMutation.isPending) return;

    try {
      await createMutation.mutateAsync({
        display_name: displayName,
        bio: bio.trim() || undefined,
      });
    } catch (err: any) {
      console.error('Failed to create worker profile:', err);
    }
  };

  const handleUpdate = async () => {
    if (!profile || updateMutation.isPending) return;

    try {
      await updateMutation.mutateAsync({
        display_name: displayName.trim() || undefined,
        bio: bio.trim() || undefined,
      });
    } catch (err: any) {
      console.error('Failed to update profile:', err);
    }
  };

  // Show loading during auth check or initial fetch
  if (authLoading || isLoading) {
    return (
      <PageWrapper
        isLoading
        loadingText="Loading worker profile..."
        className="min-h-screen bg-cream py-12 px-4"
      />
    );
  }

  // Show auth error or redirect to login
  if (isError && error) {
    if (error.status === 401) {
      navigate("/login");
      return null;
    }
    if (error.status === 404) {
      // Profile doesn't exist - this is fine, show create form
      // We'll render the create form below
    } else {
      return (
        <PageWrapper
          error={{ type: 'unknown', message: error.message || 'Failed to load worker profile' }}
          onRetry={() => refetch()}
          className="min-h-screen bg-cream py-12 px-4"
        />
      );
    }
  }

  const hasProfile = !!profile;

  return (
    <PageWrapper className="min-h-screen bg-cream py-12 px-4">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6">
          <h1 className="text-3xl font-black text-ink flex items-center gap-2">
            <Briefcase className="text-plum" size={28} />
            Earn — Worker Profile
          </h1>
          <p className="mt-2 text-ink/60">Create and manage your worker profile. One account can both hire and work.</p>
        </div>

        {/* Status Card */}
        {profile && (
          <Card className={`mb-6 border ${statusInfo[profile.onboarding_status].bg}`}>
            <div className="flex items-start gap-3">
              <Info className={`mt-0.5 ${statusInfo[profile.onboarding_status].color}`} size={20} />
              <div>
                <div className="flex items-center gap-2">
                  <span className={`font-semibold ${statusInfo[profile.onboarding_status].color}`}>
                    Status: {statusInfo[profile.onboarding_status].label}
                  </span>
                  {profile.onboarding_status === "draft" && (
                    <span className="text-xs text-ink/50">(Not visible to customers)</span>
                  )}
                </div>
                <p className="mt-1 text-sm text-ink/70">{statusInfo[profile.onboarding_status].description}</p>
              </div>
            </div>
          </Card>
        )}

        {/* Create/Edit Form */}
        <Card className="space-y-6">
          {!hasProfile ? (
            <>
              <h2 className="text-xl font-bold text-ink">Create Worker Profile</h2>
              <p className="text-sm text-ink/60">
                This profile represents you as a worker. It's separate from your customer identity.
                You can edit it anytime. Your onboarding status starts as <strong>Draft</strong> — not yet visible to customers.
              </p>

              <div className="space-y-4">
                <div className="space-y-2">
                  <label htmlFor="displayName" className="block text-sm font-medium text-ink">
                    Display Name <span className="text-rose-500">*</span>
                  </label>
                  <Input
                    id="displayName"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="How customers will see you"
                    disabled={createMutation.isPending}
                    required
                  />
                </div>

                <div className="space-y-2">
                  <label htmlFor="bio" className="block text-sm font-medium text-ink">
                    Bio (Optional)
                  </label>
                  <textarea
                    id="bio"
                    value={bio}
                    onChange={(e) => setBio(e.target.value)}
                    placeholder="Tell customers about your skills, experience, and what you offer..."
                    rows={4}
                    className="w-full rounded-lg border border-ink/15 bg-white px-4 py-3 text-sm focus:border-plum focus:outline-none focus:ring-2 focus:ring-plum/20 disabled:opacity-50"
                    disabled={createMutation.isPending}
                  />
                </div>

                {createMutation.isError && (
                  <div className="flex items-center gap-2 text-sm text-rose-600 bg-rose-50 rounded-lg p-3">
                    <AlertCircle size={16} />
                    <span>{createMutation.error?.message || 'Failed to create worker profile'}</span>
                  </div>
                )}
                {createMutation.isSuccess && (
                  <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 rounded-lg p-3">
                    <CheckCircle size={16} />
                    <span>Worker profile created! Status: Draft</span>
                  </div>
                )}

                <Button onClick={handleCreate} disabled={createMutation.isPending || !displayName.trim()} className="w-full">
                  {createMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    "Create Worker Profile"
                  )}
                </Button>
              </div>
            </>
          ) : (
            <>
              <h2 className="text-xl font-bold text-ink">Edit Worker Profile</h2>
              <p className="text-sm text-ink/60">
                Update your profile information. Your onboarding status is managed by the platform and cannot be changed directly.
              </p>

              <div className="space-y-4">
                <div className="space-y-2">
                  <label htmlFor="displayName" className="block text-sm font-medium text-ink">
                    Display Name <span className="text-rose-500">*</span>
                  </label>
                  <Input
                    id="displayName"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="How customers will see you"
                    disabled={updateMutation.isPending}
                    required
                  />
                </div>

                <div className="space-y-2">
                  <label htmlFor="bio" className="block text-sm font-medium text-ink">
                    Bio (Optional)
                  </label>
                  <textarea
                    id="bio"
                    value={bio}
                    onChange={(e) => setBio(e.target.value)}
                    placeholder="Tell customers about your skills, experience, and what you offer..."
                    rows={4}
                    className="w-full rounded-lg border border-ink/15 bg-white px-4 py-3 text-sm focus:border-plum focus:outline-none focus:ring-2 focus:ring-plum/20 disabled:opacity-50"
                    disabled={updateMutation.isPending}
                  />
                </div>

                {updateMutation.isError && (
                  <div className="flex items-center gap-2 text-sm text-rose-600 bg-rose-50 rounded-lg p-3">
                    <AlertCircle size={16} />
                    <span>{updateMutation.error?.message || 'Failed to update profile'}</span>
                  </div>
                )}
                {updateMutation.isSuccess && (
                  <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 rounded-lg p-3">
                    <CheckCircle size={16} />
                    <span>Profile updated successfully</span>
                  </div>
                )}

                <Button onClick={handleUpdate} disabled={updateMutation.isPending} className="w-full">
                  {updateMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    "Save Changes"
                  )}
                </Button>
              </div>
            </>
          )}
        </Card>

        <div className="mt-6 text-center">
          <button
            onClick={() => navigate("/dashboard")}
            className="text-sm text-ink/60 hover:text-ink underline"
          >
            ← Back to Dashboard
          </button>
        </div>
      </div>
    </PageWrapper>
  );
}