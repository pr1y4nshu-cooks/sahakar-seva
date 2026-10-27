import { Briefcase, Loader2, Save, AlertCircle, CheckCircle, Info } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { api, type WorkerProfile } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

type OnboardingStatus = WorkerProfile["onboarding_status"];

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
  const [profile, setProfile] = useState<WorkerProfile | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [hasProfile, setHasProfile] = useState(false);

  useEffect(() => {
    async function loadProfile() {
      if (!session?.access_token) {
        navigate("/login");
        return;
      }

      try {
        const data = await api.getMyWorkerProfile(session.access_token);
        setProfile(data);
        setDisplayName(data.display_name);
        setBio(data.bio ?? "");
        setHasProfile(true);
      } catch (err: any) {
        if (err.status === 404) {
          setHasProfile(false);
        } else if (err.status === 401) {
          navigate("/login");
        } else {
          setError("Failed to load worker profile");
        }
      } finally {
        setLoading(false);
      }
    }

    if (!authLoading) {
      loadProfile();
    }
  }, [authLoading, session, navigate]);

  const handleCreate = async () => {
    if (!session?.access_token || saving) return;
    if (!displayName.trim()) {
      setError("Display name is required");
      return;
    }

    setError(null);
    setSuccess(null);
    setSaving(true);

    try {
      const data = await api.createWorkerProfile(session.access_token, {
        display_name: displayName,
        bio: bio.trim() || undefined,
      });
      setProfile(data);
      setDisplayName(data.display_name);
      setBio(data.bio ?? "");
      setHasProfile(true);
      setSuccess("Worker profile created! Status: Draft");
    } catch (err: any) {
      if (err.status === 409) {
        setError("You already have a worker profile");
      } else {
        setError(err.message || "Failed to create worker profile");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async () => {
    if (!session?.access_token || !profile || saving) return;

    setError(null);
    setSuccess(null);
    setSaving(true);

    try {
      const data = await api.updateMyWorkerProfile(session.access_token, {
        display_name: displayName.trim() || undefined,
        bio: bio.trim() || undefined,
      });
      setProfile(data);
      setDisplayName(data.display_name);
      setBio(data.bio ?? "");
      setSuccess("Profile updated successfully");
    } catch (err: any) {
      setError(err.message || "Failed to update profile");
    } finally {
      setSaving(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream">
        <Loader2 className="h-8 w-8 animate-spin text-plum" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-cream py-12 px-4">
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
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDisplayName(e.target.value)}
                    placeholder="How customers will see you"
                    disabled={saving}
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
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setBio(e.target.value)}
                    placeholder="Tell customers about your skills, experience, and what you offer..."
                    rows={4}
                    className="w-full rounded-lg border border-ink/15 bg-white px-4 py-3 text-sm focus:border-plum focus:outline-none focus:ring-2 focus:ring-plum/20 disabled:opacity-50"
                    disabled={saving}
                  />
                </div>

                {error && (
                  <div className="flex items-center gap-2 text-sm text-rose-600 bg-rose-50 rounded-lg p-3">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                  </div>
                )}
                {success && (
                  <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 rounded-lg p-3">
                    <CheckCircle size={16} />
                    <span>{success}</span>
                  </div>
                )}

                <Button onClick={handleCreate} disabled={saving || !displayName.trim()} className="w-full">
                  {saving ? (
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
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDisplayName(e.target.value)}
                    placeholder="How customers will see you"
                    disabled={saving}
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
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setBio(e.target.value)}
                    placeholder="Tell customers about your skills, experience, and what you offer..."
                    rows={4}
                    className="w-full rounded-lg border border-ink/15 bg-white px-4 py-3 text-sm focus:border-plum focus:outline-none focus:ring-2 focus:ring-plum/20 disabled:opacity-50"
                    disabled={saving}
                  />
                </div>

                {error && (
                  <div className="flex items-center gap-2 text-sm text-rose-600 bg-rose-50 rounded-lg p-3">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                  </div>
                )}
                {success && (
                  <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 rounded-lg p-3">
                    <CheckCircle size={16} />
                    <span>{success}</span>
                  </div>
                )}

                <Button onClick={handleUpdate} disabled={saving} className="w-full">
                  {saving ? (
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
    </div>
  );
}