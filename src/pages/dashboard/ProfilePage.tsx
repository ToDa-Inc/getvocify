import { useState, useEffect, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, Loader2, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { useAuth } from "@/features/auth";
import { authApi, authKeys } from "@/features/auth/api";
import { getUserInitials } from "@/features/auth/types";
import { CRM_EMAIL_MATCH_HINT, WHATSAPP_PHONE_HINT } from "@/lib/identity-hints";

function apiErrorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "data" in error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

const ChangePasswordCard = ({ email }: { email?: string }) => {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [resetSending, setResetSending] = useState(false);

  const handleChange = async (event: FormEvent) => {
    event.preventDefault();
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("New passwords do not match");
      return;
    }
    setIsSaving(true);
    try {
      await authApi.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast.success("Password updated. We emailed this account.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not update password"));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
      <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-2`}>Password</h2>
      <p className="text-xs text-muted-foreground mb-8 leading-relaxed">
        This login is yours. We email this account when the password changes. Teammates keep their own passwords.
      </p>
      <form onSubmit={handleChange} className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="current-password" className={THEME_TOKENS.typography.capsLabel}>
            Current password
          </label>
          <Input
            id="current-password"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
          />
        </div>
        <div className="grid sm:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label htmlFor="new-password" className={THEME_TOKENS.typography.capsLabel}>
              New password
            </label>
            <Input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="confirm-password" className={THEME_TOKENS.typography.capsLabel}>
              Confirm new password
            </label>
            <Input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
        <Button
          type="submit"
          disabled={isSaving}
          className="rounded-lg px-6 h-11 bg-beige text-cream"
        >
          {isSaving ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Updating...
            </>
          ) : (
            "Update password"
          )}
        </Button>
        {email ? (
          <button
            type="button"
            disabled={resetSending}
            className="text-xs text-beige hover:underline disabled:opacity-50"
            onClick={async () => {
              setResetSending(true);
              try {
                await authApi.requestPasswordReset(email);
                toast.success("If this account exists, we sent a reset link.");
              } catch {
                toast.error("Could not send reset email");
              } finally {
                setResetSending(false);
              }
            }}
          >
            {resetSending ? "Sending reset email…" : "Forgot current password? Email me a reset link"}
          </button>
        ) : null}
        </div>
      </form>
    </div>
  );
};

const ProfilePage = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState(user?.fullName ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (user) {
      setFullName(user.fullName ?? "");
      setPhone(user.phone ?? "");
    }
  }, [user]);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const updates: { fullName?: string; phone?: string } = {};
      if (fullName.trim()) updates.fullName = fullName.trim();
      updates.phone = phone.trim();
      const updated = await authApi.updateProfile(updates);
      queryClient.setQueryData(authKeys.me(), updated);
      toast.success("Profile saved successfully");
    } catch (error) {
      toast.error("Failed to save profile");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={`max-w-2xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Mi <span className={THEME_TOKENS.typography.accentTitle}>perfil</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Gestiona tu perfil.</p>
      </div>

      {/* Profile */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-8`}>Profile</h2>

        <div className="flex items-center gap-8 mb-8 pb-8 border-b border-border/40">
          <div className="relative">
            <div
              className={`w-24 h-24 ${THEME_TOKENS.radius.pill} bg-secondary/10 flex items-center justify-center border-4 border-white shadow-medium`}
            >
              <span className="text-2xl font-semibold text-beige">
                {user ? getUserInitials(user) : "?"}
              </span>
            </div>
            <button
              className={`absolute -bottom-1 -right-1 w-10 h-10 ${THEME_TOKENS.radius.pill} bg-beige text-cream flex items-center justify-center shadow-medium hover:bg-beige-dark transition-colors border-4 border-white`}
            >
              <Camera className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-1">
            <p className="font-bold text-foreground text-lg">Profile Photo</p>
            <p className="text-sm text-muted-foreground">JPG, PNG, or GIF. Max 2MB</p>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Full Name</label>
            <Input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your name"
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
            />
            <p className="text-xs text-muted-foreground leading-relaxed">
              Shown as the label on your calls and memos.
            </p>
          </div>
          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Email</label>
            <Input
              value={user?.email || ""}
              disabled
              placeholder="Email from account"
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold opacity-50"
            />
            <p className="text-xs text-muted-foreground leading-relaxed">
              {CRM_EMAIL_MATCH_HINT} Email is set at signup and cannot be changed here.
            </p>
          </div>
          <div className="sm:col-span-2 space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>WhatsApp phone</label>
            <Input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+34600111222"
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
            />
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              {WHATSAPP_PHONE_HINT}
            </p>
          </div>
        </div>

        <div className="mt-10">
          <Button
            onClick={handleSave}
            disabled={isSaving}
            className="rounded-lg px-6 h-11 bg-beige text-cream"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Changes"
            )}
          </Button>
        </div>
      </div>

      <ChangePasswordCard email={user?.email} />

      {/* Log out */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <Button
          variant="outline"
          className="w-full rounded-full px-8 h-12 border-border/40 text-muted-foreground hover:text-destructive hover:border-destructive/30 hover:bg-destructive/5 transition-colors"
          onClick={async () => {
            await logout();
            navigate("/login", { replace: true });
          }}
        >
          <LogOut className="h-4 w-4 mr-2" />
          Log out
        </Button>
      </div>
    </div>
  );
};

export default ProfilePage;
