import { Eye, EyeOff, Loader2, Mail, Lock, AlertCircle, CheckCircle } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageWrapper, ErrorState } from "@/components/ui/States";

export function Signup() {
  const navigate = useNavigate();
  const { signUp, loading: authLoading, isFixturesMode } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setLoading(true);

    const { error: authError, user } = await signUp(email, password);
    setLoading(false);

    if (authError) {
      if (authError.code === 'EMAIL_CONFIRMATION_REQUIRED') {
        setSuccess("Account created! Please check your email to confirm your address.");
        setTimeout(() => navigate("/login"), 3000);
      } else {
        setError(authError.message || "Failed to create account");
      }
    } else if (user) {
      setSuccess("Account created successfully!");
      setTimeout(() => navigate("/dashboard"), 1000);
    }
  };

  return (
    <PageWrapper className="min-h-screen">
      <div className="flex items-center justify-center bg-cream px-4 py-12">
        <Card className="w-full max-w-md">
          <div className="text-center mb-8">
            <Link to="/" className="inline-flex items-center gap-2 text-2xl font-black text-ink">
              SAHAKAR<span className="text-plum">–</span>SEVA
            </Link>
            <h1 className="mt-6 text-2xl font-bold text-ink">Create an account</h1>
            <p className="mt-2 text-sm text-ink/60">Join SAHAKAR–SEVA to hire, work, or both</p>
            {isFixturesMode && (
              <p className="mt-2 text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded">
                Dev fixtures mode — use any email/password
              </p>
            )}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <ErrorState
                type="validation"
                message={error}
                onAction={{ label: "Try Again", onClick: () => setError(null) }}
              />
            )}
            {success && (
              <div className="flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 rounded-lg p-3">
                <CheckCircle size={16} />
                <span>{success}</span>
              </div>
            )}

            <div className="space-y-2">
              <label htmlFor="email" className="block text-sm font-medium text-ink">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={18} />
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="pl-10"
                  required
                  disabled={loading || authLoading}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="block text-sm font-medium text-ink">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={18} />
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  className="pl-10 pr-10"
                  required
                  disabled={loading || authLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink/40 hover:text-ink"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-ink">
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/40" size={18} />
                <Input
                  id="confirmPassword"
                  type={showPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  className="pl-10"
                  required
                  disabled={loading || authLoading}
                />
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={loading || authLoading}>
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Creating account...
                </>
              ) : (
                "Create account"
              )}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-ink/60">
            Already have an account?{" "}
            <Link to="/login" className="text-plum font-medium hover:underline">
              Sign in
            </Link>
          </p>

          <p className="mt-4 text-center text-xs text-ink/50">
            By creating an account, you agree to our Terms of Service and Privacy Policy.
          </p>
        </Card>
      </div>
    </PageWrapper>
  );
}