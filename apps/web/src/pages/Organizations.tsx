import { Building2, Loader2, Plus, AlertCircle, CheckCircle, Users, AlertTriangle, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { useMyOrganizations, useCreateOrganization } from "@/hooks/useApi";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { PageWrapper, ErrorState } from "@/components/ui/States";
import { OrgDashboard } from "@/components/trust/OrgDashboard";

export function Organizations() {
  const navigate = useNavigate();
  const { session, loading: authLoading } = useAuth();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [name, setName] = useState("");
  const [orgType, setOrgType] = useState<"business" | "cooperative">("business");

  const { data: organizations = [], isLoading, error, refetch } = useMyOrganizations({
    enabled: !!session?.access_token && !authLoading,
  });

  const createMutation = useCreateOrganization();

  const handleCreate = async () => {
    if (!name.trim() || createMutation.isPending) return;

    try {
      await createMutation.mutateAsync({
        name: name.trim(),
        organization_type: orgType,
      });
      setName("");
      setOrgType("business");
      setShowCreateModal(false);
    } catch (err: any) {
      console.error('Failed to create organization:', err);
    }
  };

  // Show loading during auth check or initial fetch
  if (authLoading || isLoading) {
    return (
      <PageWrapper
        isLoading
        loadingText="Loading organizations..."
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
        error={{ type: 'unknown', message: error.message || 'Failed to load organizations' }}
        onRetry={() => refetch()}
        className="min-h-screen bg-cream py-12 px-4"
      />
    );
  }

  const roleLabels: Record<string, { label: string; color: string; bg: string }> = {
    owner: { label: "Owner", color: "text-plum", bg: "bg-plum/10" },
    admin: { label: "Admin", color: "text-blue-700", bg: "bg-blue-50" },
    member: { label: "Member", color: "text-ink/60", bg: "bg-ink/5" },
  };

  return (
    <PageWrapper className="min-h-screen bg-cream py-12 px-4">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-black text-ink flex items-center gap-2">
              <Building2 className="text-plum" size={28} />
              Organizations
            </h1>
            <p className="mt-2 text-ink/60">Create and manage businesses or cooperatives</p>
          </div>
          <Button onClick={() => setShowCreateModal(true)} className="gap-2">
            <Plus size={18} />
            Create Organization
          </Button>
        </div>

        {createMutation.isError && (
          <div className="mb-6 flex items-center gap-2 text-sm text-rose-600 bg-rose-50 rounded-lg p-3">
            <AlertCircle size={16} />
            <span>{createMutation.error?.message || 'Failed to create organization'}</span>
          </div>
        )}
        {createMutation.isSuccess && (
          <div className="mb-6 flex items-center gap-2 text-sm text-emerald-600 bg-emerald-50 rounded-lg p-3">
            <CheckCircle size={16} />
            <span>{orgType === "business" ? "Business" : "Cooperative"} created successfully!</span>
          </div>
        )}

        {/* Organizations List */}
        <Card className="mb-6">
          {organizations.length === 0 ? (
            <div className="py-12 text-center">
              <Building2 className="mx-auto h-12 w-12 text-ink/20" />
              <h3 className="mt-4 text-lg font-medium text-ink">No organizations yet</h3>
              <p className="mt-2 text-sm text-ink/60 max-w-xs mx-auto">
                Create a business or cooperative to manage team members and post jobs on behalf of your organization.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-ink">Your Organizations</h2>
              {organizations.map((org) => {
                const roleInfo = roleLabels[org.my_membership_role] ?? {
                  label: org.my_membership_role,
                  color: "text-ink/60",
                  bg: "bg-ink/5",
                };
                const typeInfo = org.organization_type === "business"
                  ? { label: "Business", icon: Building2 }
                  : { label: "Cooperative", icon: Users };
                const TypeIcon = typeInfo.icon;

                return (
                  <div
                    key={org.id}
                    className="p-4 rounded-lg border border-[#eee8f2] bg-white"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-lg bg-plum/10 flex items-center justify-center">
                          <TypeIcon className="h-5 w-5 text-plum" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold text-ink">{org.name}</h3>
                            <span className={`px-2 py-0.5 text-xs rounded-full ${roleInfo.bg} ${roleInfo.color}`}>
                              {roleInfo.label}
                            </span>
                            <span className="px-2 py-0.5 text-xs rounded-full bg-ink/5 text-ink/60">
                              {typeInfo.label}
                            </span>
                          </div>
                          <p className="mt-1 text-sm text-ink/60">Created {new Date(org.created_at).toLocaleDateString()}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {org.my_membership_role === "owner" && (
                          <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded-full">
                            <AlertTriangle size={10} />
                            Full control
                          </span>
                        )}
                      </div>
                    </div>
                    {(org.my_membership_role === "owner" || org.my_membership_role === "admin") && <OrgDashboard orgId={org.id} />}
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Create Organization Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
              <div className="p-6 border-b border-[#eee8f2] flex items-center justify-between">
                <h2 className="text-xl font-bold text-ink">Create Organization</h2>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="text-ink/40 hover:text-ink"
                  aria-label="Close"
                >
                  <X size={20} />
                </button>
              </div>
              <div className="p-6 space-y-4">
                <p className="text-sm text-ink/60">
                  Choose the type of organization. You will automatically become the owner.
                </p>

                <div className="space-y-2">
                  <label className="block text-sm font-medium text-ink">Name <span className="text-rose-500">*</span></label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g., Smith Plumbing Co."
                    disabled={createMutation.isPending}
                  />
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-medium text-ink">Type</label>
                  <div className="grid grid-cols-2 gap-3">
                    {(["business", "cooperative"] as const).map((type) => {
                      const typeInfo = type === "business"
                        ? { label: "Business", icon: Building2, desc: "Standard company or sole proprietorship" }
                        : { label: "Cooperative", icon: Users, desc: "Member-owned collective (no legal claim implied)" };
                      const TypeIcon = typeInfo.icon;
                      return (
                        <button
                          key={type}
                          onClick={() => setOrgType(type)}
                          className={`relative p-4 rounded-lg border-2 transition-all text-left ${
                            orgType === type
                              ? "border-plum bg-plum/5"
                              : "border-ink/10 hover:border-plum/30"
                          }`}
                        >
                          <input
                            type="radio"
                            name="orgType"
                            value={type}
                            checked={orgType === type}
                            onChange={() => setOrgType(type)}
                            className="sr-only"
                          />
                          <div className="flex items-center gap-3">
                            <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${orgType === type ? "bg-plum text-white" : "bg-ink/5 text-ink/60"}`}>
                              <TypeIcon className="h-4 w-4" />
                            </div>
                            <div>
                              <p className="font-medium text-ink">{typeInfo.label}</p>
                              <p className="text-xs text-ink/50">{typeInfo.desc}</p>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {createMutation.isError && (
                  <div className="flex items-center gap-2 text-sm text-rose-600 bg-rose-50 rounded-lg p-3">
                    <AlertCircle size={16} />
                    <span>{createMutation.error?.message || 'Failed to create organization'}</span>
                  </div>
                )}

                <div className="flex gap-3 pt-2">
                  <Button
                    onClick={() => setShowCreateModal(false)}
                    disabled={createMutation.isPending}
                    className="flex-1 border border-ink/10 bg-white text-ink/60 hover:bg-ink/5"
                  >
                    Cancel
                  </Button>
                  <Button onClick={handleCreate} disabled={createMutation.isPending || !name.trim()} className="flex-1">
                    {createMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      "Create Organization"
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageWrapper>
  );
}