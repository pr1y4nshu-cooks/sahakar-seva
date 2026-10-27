import { Loader2, Save, User, Mail, AlertCircle, CheckCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";

export function Profile() {
  const navigate = useNavigate();
  const { user, session, loading: authLoading } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    async function loadProfile() {
      if (!session?.access_token) {
        navigate("/login");
        return;
      }

      try {
        const data = await api.getCurrentUser(session.access_token);
        setDisplayName(data.display_name);
      } catch (err: any) {
        if (err.status === 401) {
          navigate("/login");
        } else {
          setError("Failed to load profile");
        }
      } finally {
        setLoading(false);
      }
    }

    if (!authLoading) {
      loadProfile();
    }
  }, [authLoading, session, navigate]);

  const handleSave = async () => {
    if (!session?.access_token || saving) return;

    setError(null);
    setSuccess(null);
    setSaving(true);

    try {
      await api.updateCurrentUser(session.access_token, { display_name: displayName });
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

  if (!user) {
    return null; // Handled by navigate
  }

  return (
    <div className="min-h-screen bg-cream py-12 px-4">
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
              <h2 className="text-xl font-bold text-ink">{displayName || "Your Name"}</h2>
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
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDisplayName(e.target.value)}
                placeholder="Enter your display name"
                disabled={saving}
              />
            </div>

            <div className="flex items-center gap-3 pt-2">
              <Button onClick={handleSave} disabled={saving || !displayName.trim()}>
                {saving ? (
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

              {error && (
                <span className="flex items-center gap-1 text-sm text-rose-600">
                  <AlertCircle size={14} />
                  {error}
                </span>
              )}
              {success && (
                <span className="flex items-center gap-1 text-sm text-emerald-600">
                  <CheckCircle size={14} />
                  {success}
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
    </div>
  );
}