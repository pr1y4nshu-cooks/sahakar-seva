import { Loader2, Save, User, AlertCircle, CheckCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useCurrentUser, useUpdateCurrentUser } from "@/hooks/useApi";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageWrapper, EmptyState, ErrorState } from "@/components/ui/States";

export function Profile() {
  const navigate = useNavigate();
  const { session, loading: authLoading } = useAuth();
  const [displayName, setDisplayName] = useState("");

  const { data: user, isLoading, error, refetch } = useCurrentUser({
    enabled: !!session?.access_token && !authLoading,
  });

  const updateMutation = useUpdateCurrentUser();

  // Load display name when user data arrives
  // Using a separate effect to avoid stale closure issues
  // biome-ignore lint/correctness/useExhaustiveDependencies: displayName should update when user changes
  const userEffect = () => {
    if (user && !displayName) {
      setDisplayName(user.display_name);
    }
  };
  // We'll call this inline in the render

  const handleSave = async () => {
    if (!displayName.trim() || updateMutation.isPending) return;

    try {
      await updateMutation.mutateAsync({ display_name: displayName.trim() });
      // Success - query client cache is updated automatically
    } catch (err: any) {
      // Error handling is done by the mutation's onError or component error boundary
      console.error('Failed to update profile:', err);
    }
  };

  // Show loading during auth check or initial fetch
  if (authLoading || isLoading) {
    return (
      <PageWrapper
        isLoading
        loadingText="Loading profile..."
        className="min-h-screen bg-cream py-12 px-4"
      />
    );
  }

  // Show auth error or redirect to login
  if (error) {
    if (error.status === 401) {
      navigate("/login");
      return null;
    }
    return (
      <PageWrapper
        error={{ type: 'unknown', message: error.message || 'Failed to load profile' }}
        onRetry={() => refetch()}
        className="min-h-screen bg-cream py-12 px-4"
      />
    );
  }

  if (!user) {
    return null; // Navigation handled by ProtectedRoute
  }

  // Update displayName when user data loads (side effect pattern)
  // In production, consider using useEffect or a derived state approach
  if (user && !displayName) {
    setDisplayName(user.display_name);
  }

  return (
    <PageWrapper className="min-h-screen bg-cream py-12 px-4">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6">
          <h1 className="text-3xl font-black text-ink">My Profile</h1>
          <p className="mt-2 text-ink/60">Manage your account settings</p>
        </div>

        <Card className="space-y-6">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-full bg-plum/10 flex items-center justify-center">
              <User className="h-8 w-8 text-plum" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-ink">{user.display_name}</h2>
              <p className="text-sm text-ink/60">{user.email}</p>
            </div>
          </div>

          <div className="border-t border-[#eee8f2] pt-6 space-y-4">
            <h3 className="font-semibold text-ink">Display Name</h3>
            <div className="space-y-2">
              <label htmlFor="displayName" className="block text-sm font-medium text-ink">
                How others see you
              </label>
              <Input
                id="displayName"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Enter your display name"
                disabled={updateMutation.isPending}
              />
            </div>

            <div className="flex items-center gap-3 pt-2">
              <Button
                onClick={handleSave}
                disabled={updateMutation.isPending || !displayName.trim()}
              >
                {updateMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="mr-2 h-4 w-4" />
                    Save Changes
                  </>
                )}
              </Button>

              {updateMutation.isError && (
                <span className="flex items-center gap-1 text-sm text-rose-600">
                  <AlertCircle size={14} />
                  {updateMutation.error?.message || 'Failed to update profile'}
                </span>
              )}
              {updateMutation.isSuccess && (
                <span className="flex items-center gap-1 text-sm text-emerald-600">
                  <CheckCircle size={14} />
                  Profile updated successfully
                </span>
              )}
            </div>
          </div>

          <div className="border-t border-[#eee8f2] pt-6 space-y-4">
            <h3 className="font-semibold text-ink">Email</h3>
            <p className="text-sm text-ink/60">Email changes will be available after email verification is implemented.</p>
            <p className="text-sm font-medium text-ink/80">{user.email}</p>
          </div>
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