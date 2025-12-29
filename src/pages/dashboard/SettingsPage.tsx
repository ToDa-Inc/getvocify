import { useState } from "react";
import { Camera, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

const SettingsPage = () => {
  const [autoApprove, setAutoApprove] = useState(true);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [slackNotifications, setSlackNotifications] = useState(false);

  const handleSave = () => {
    toast.success("Settings saved successfully");
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="text-muted-foreground">Manage your account and preferences</p>
      </div>

      {/* Profile */}
      <div className="bg-card rounded-2xl shadow-soft p-6">
        <h2 className="text-lg font-semibold text-foreground mb-6">Profile</h2>
        
        <div className="flex items-center gap-6 mb-6">
          <div className="relative">
            <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-2xl font-bold text-primary">JD</span>
            </div>
            <button className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-medium hover:bg-primary/80 transition-colors">
              <Camera className="h-4 w-4" />
            </button>
          </div>
          <div>
            <p className="font-medium text-foreground">Profile Photo</p>
            <p className="text-sm text-muted-foreground">JPG, PNG, or GIF. Max 2MB</p>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-foreground mb-1.5 block">Full Name</label>
            <Input defaultValue="John Doe" className="bg-input" />
          </div>
          <div>
            <label className="text-sm font-medium text-foreground mb-1.5 block">Email</label>
            <Input defaultValue="john@company.com" disabled className="bg-muted" />
          </div>
          <div className="sm:col-span-2">
            <label className="text-sm font-medium text-foreground mb-1.5 block">Phone (optional)</label>
            <Input placeholder="+1 (555) 000-0000" className="bg-input" />
          </div>
        </div>

        <div className="mt-6">
          <Button onClick={handleSave}>Save Changes</Button>
        </div>
      </div>

      {/* Preferences */}
      <div className="bg-card rounded-2xl shadow-soft p-6">
        <h2 className="text-lg font-semibold text-foreground mb-6">Preferences</h2>
        
        <div className="space-y-6">
          <div>
            <label className="text-sm font-medium text-foreground mb-1.5 block">Default CRM</label>
            <select className="w-full h-10 px-3 rounded-xl border border-border bg-input text-foreground">
              <option>HubSpot</option>
              <option>Salesforce</option>
              <option>Pipedrive</option>
              <option>GoHighLevel</option>
            </select>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-foreground">Auto-approve high confidence updates</p>
              <p className="text-sm text-muted-foreground">Automatically approve updates with 95%+ confidence</p>
            </div>
            <Switch checked={autoApprove} onCheckedChange={setAutoApprove} />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-foreground">Email notifications</p>
              <p className="text-sm text-muted-foreground">Get notified when memos are processed</p>
            </div>
            <Switch checked={emailNotifications} onCheckedChange={setEmailNotifications} />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-foreground">Slack notifications</p>
              <p className="text-sm text-muted-foreground">Send updates to your Slack channel</p>
            </div>
            <div className="flex items-center gap-3">
              {!slackNotifications && (
                <Button variant="outline" size="sm">Connect Slack</Button>
              )}
              <Switch checked={slackNotifications} onCheckedChange={setSlackNotifications} />
            </div>
          </div>
        </div>
      </div>

      {/* Billing */}
      <div className="bg-card rounded-2xl shadow-soft p-6">
        <h2 className="text-lg font-semibold text-foreground mb-6">Billing</h2>
        
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-foreground">Current Plan</p>
            <span className="font-semibold text-foreground">Basic - $25/month</span>
          </div>
          <div className="flex items-center justify-between">
            <p className="text-foreground">Next billing date</p>
            <span className="text-muted-foreground">January 29, 2026</span>
          </div>
          <div className="flex items-center justify-between">
            <p className="text-foreground">Usage</p>
            <span className="text-muted-foreground">12 / Unlimited memos this month</span>
          </div>
        </div>

        <div className="flex items-center gap-4 mt-6 pt-6 border-t border-border">
          <Button variant="hero">Upgrade to Pro</Button>
          <button className="text-sm text-muted-foreground hover:text-foreground transition-colors">
            Cancel subscription
          </button>
        </div>
      </div>

      {/* Danger Zone */}
      <div className="bg-card rounded-2xl shadow-soft p-6 border-2 border-destructive/20">
        <h2 className="text-lg font-semibold text-destructive mb-2">Danger Zone</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Once you delete your account, there is no going back. Please be certain.
        </p>
        <Button variant="outline" className="border-destructive text-destructive hover:bg-destructive hover:text-destructive-foreground">
          <Trash2 className="h-4 w-4 mr-2" />
          Delete Account
        </Button>
      </div>
    </div>
  );
};

export default SettingsPage;
