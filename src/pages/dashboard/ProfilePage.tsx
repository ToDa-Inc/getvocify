import { useState, useEffect } from "react";
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
          </div>
          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Email</label>
            <Input
              value={user?.email || ""}
              disabled
              placeholder="Email from account"
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold opacity-50"
            />
          </div>
          <div className="sm:col-span-2 space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Phone (optional)</label>
            <Input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1 (555) 000-0000"
              className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Add your WhatsApp number for voice-to-CRM via WhatsApp
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

      {/* Log out */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <Button
          variant="outline"
          className="w-full rounded-full px-8 h-12 border-border/40 text-muted-foreground hover:text-destructive hover:border-destructive/30 hover:bg-destructive/5 transition-colors"
          onClick={async () => {
            await logout();
            navigate("/");
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
