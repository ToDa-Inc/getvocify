import { useState, useEffect } from "react";
import { Camera, Trash2, ShieldCheck, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { HubSpotConfiguration } from "@/components/dashboard/hubspot/HubSpotConfiguration";
import { crmApi } from "@/lib/api/crm";

const SettingsPage = () => {
  const [autoApprove, setAutoApprove] = useState(true);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [slackNotifications, setSlackNotifications] = useState(false);
  const [isHubSpotConnected, setIsHubSpotConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const config = await crmApi.getConfiguration();
        setIsHubSpotConnected(!!config);
      } catch (error) {
        console.error("Failed to check connection", error);
      } finally {
        setIsLoading(false);
      }
    };
    checkConnection();
  }, []);

  const handleSave = () => {
    toast.success("Settings saved successfully");
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <Loader2 className="h-10 w-10 animate-spin text-beige" />
        <p className={THEME_TOKENS.typography.capsLabel}>Loading Settings...</p>
      </div>
    );
  }

  return (
    <div className={`max-w-2xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Account <span className={THEME_TOKENS.typography.accentTitle}>Settings</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Manage your profile, preferences, and billing.</p>
      </div>

      {/* HubSpot Configuration */}
      {isHubSpotConnected && (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10 border-2 border-beige/10`}>
          <div className="flex items-center gap-4 mb-10">
            <div className="w-12 h-12 rounded-2xl bg-beige/10 flex items-center justify-center">
              <ShieldCheck className="h-6 w-6 text-beige" />
            </div>
            <div>
              <h2 className={THEME_TOKENS.typography.sectionTitle}>HubSpot Configuration</h2>
              <p className="text-xs text-muted-foreground mt-1">Manage your pipeline and field mapping preferences.</p>
            </div>
          </div>
          
          <HubSpotConfiguration />
        </div>
      )}

      {/* Profile */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-8`}>Profile</h2>
        
        <div className="flex items-center gap-8 mb-8 pb-8 border-b border-border/40">
          <div className="relative">
            <div className={`w-24 h-24 ${THEME_TOKENS.radius.pill} bg-secondary/10 flex items-center justify-center border-4 border-white shadow-medium`}>
              <span className="text-3xl font-black text-beige">JD</span>
            </div>
            <button className={`absolute -bottom-1 -right-1 w-10 h-10 ${THEME_TOKENS.radius.pill} bg-beige text-cream flex items-center justify-center shadow-medium hover:bg-beige-dark transition-colors border-4 border-white`}>
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
            <Input defaultValue="John Doe" className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold" />
          </div>
          <div className="space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Email</label>
            <Input defaultValue="john@company.com" disabled className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold opacity-50" />
          </div>
          <div className="sm:col-span-2 space-y-2">
            <label className={THEME_TOKENS.typography.capsLabel}>Phone (optional)</label>
            <Input placeholder="+1 (555) 000-0000" className="bg-secondary/5 border-border/40 rounded-full px-6 h-12 font-bold" />
          </div>
        </div>

        <div className="mt-10">
          <Button onClick={handleSave} className="rounded-full px-8 h-12 bg-beige text-cream shadow-medium hover:scale-105 transition-transform">
            Save Changes
          </Button>
        </div>
      </div>

      {/* Preferences */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-8`}>Preferences</h2>
        
        <div className="space-y-8">
          <div className="space-y-3">
            <label className={THEME_TOKENS.typography.capsLabel}>Default CRM</label>
            <select className="w-full h-12 px-6 rounded-full border border-border/40 bg-secondary/5 text-foreground appearance-none cursor-pointer font-bold focus:outline-none">
              <option>HubSpot</option>
              <option disabled>Salesforce (Coming Soon)</option>
              <option disabled>Pipedrive (Coming Soon)</option>
            </select>
          </div>

          <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
            <div>
              <p className="font-bold text-foreground">Auto-approve updates</p>
              <p className="text-xs text-muted-foreground mt-0.5 tracking-tight">Approve updates with 95%+ confidence</p>
            </div>
            <Switch checked={autoApprove} onCheckedChange={setAutoApprove} />
          </div>

          <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
            <div>
              <p className="font-bold text-foreground">Email notifications</p>
              <p className="text-xs text-muted-foreground mt-0.5 tracking-tight">Get notified when memos are processed</p>
            </div>
            <Switch checked={emailNotifications} onCheckedChange={setEmailNotifications} />
          </div>

          <div className="flex items-center justify-between p-4 rounded-2xl bg-secondary/5 border border-border/20">
            <div className="flex-1">
              <p className="font-bold text-foreground">Slack Integration</p>
              <p className="text-xs text-muted-foreground mt-0.5 tracking-tight">Send updates to your Slack channel</p>
            </div>
            <div className="flex items-center gap-4">
              {!slackNotifications && (
                <Button variant="outline" size="sm" className="rounded-full px-4 text-[10px] font-black uppercase tracking-widest border-border/50">
                  Connect
                </Button>
              )}
              <Switch checked={slackNotifications} onCheckedChange={setSlackNotifications} />
            </div>
          </div>
        </div>
      </div>

      {/* Billing */}
      <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-10 relative overflow-hidden group`}>
        <div className="absolute inset-0 bg-gradient-to-br from-beige/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-10`}>Billing & Subscription</h2>
        
        <div className="space-y-6 relative z-10">
          <div className="flex items-center justify-between py-2 border-b border-foreground/5">
            <p className={`${THEME_TOKENS.typography.capsLabel} !text-muted-foreground/60`}>Current Plan</p>
            <span className="font-bold text-foreground">Basic - $25/month</span>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-foreground/5">
            <p className={`${THEME_TOKENS.typography.capsLabel} !text-muted-foreground/60`}>Next Billing Date</p>
            <span className="text-foreground font-medium">January 29, 2026</span>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-foreground/5">
            <p className={`${THEME_TOKENS.typography.capsLabel} !text-muted-foreground/60`}>Monthly Usage</p>
            <span className="text-foreground font-medium">12 / Unlimited memos</span>
          </div>
        </div>

        <div className="flex items-center gap-6 mt-10 relative z-10">
          <Button variant="hero" className="rounded-full px-8 py-4 bg-beige text-cream hover:bg-beige-dark shadow-large hover:scale-105 transition-transform text-[10px] font-black uppercase tracking-widest">
            Upgrade to Pro
          </Button>
          <button className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/30 hover:text-foreground transition-colors">
            Cancel subscription
          </button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10 border-2 border-destructive/20 bg-destructive/[0.02]`}>
        <h2 className="text-xl font-bold text-destructive mb-2 tracking-tight">Danger Zone</h2>
        <p className="text-sm text-muted-foreground mb-8 leading-relaxed">
          Once you delete your account, there is no going back. All your voice memos and CRM sync history will be permanently erased.
        </p>
        <Button variant="outline" className="border-destructive/50 text-destructive hover:bg-destructive hover:text-white rounded-full px-8 h-12 text-[10px] font-black uppercase tracking-widest transition-all">
          <Trash2 className="h-4 w-4 mr-2" />
          Delete Account Permanently
        </Button>
      </div>
    </div>
  );
};

export default SettingsPage;
