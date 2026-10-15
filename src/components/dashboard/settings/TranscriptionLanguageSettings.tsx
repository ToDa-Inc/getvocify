import { useState } from "react";
import { Globe, Languages } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Toggle } from "@/components/ui/toggle";
import { toast } from "sonner";
import { SettingsRow } from "@/components/ui/settings-card";
import { useAuth } from "@/features/auth";
import { authApi, authKeys } from "@/features/auth/api";
import type { User } from "@/features/auth/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const OPTIONS = [
  { code: "es", label: "Spanish" },
  { code: "en", label: "English" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "it", label: "Italian" },
  { code: "pt", label: "Portuguese" },
  { code: "ca", label: "Catalan" },
] as const;

function packLanguages(primary: string, extras: string[]): string[] {
  const main = OPTIONS.some((o) => o.code === primary) ? primary : "es";
  const rest = extras.filter((c) => c !== main && OPTIONS.some((o) => o.code === c));
  return [main, ...rest];
}

function unpack(user: User | null | undefined) {
  const langs = user?.sttLanguages?.length ? user.sttLanguages : ["es"];
  return { primary: langs[0] || "es", extras: langs.slice(1) };
}

export const TranscriptionLanguageSettings = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const { primary, extras } = unpack(user);

  const save = async (nextPrimary: string, nextExtras: string[]) => {
    setSaving(true);
    try {
      const updated = await authApi.updateProfile({ sttLanguages: packLanguages(nextPrimary, nextExtras) });
      queryClient.setQueryData<User>(authKeys.me(), updated);
    } catch {
      toast.error("Could not save transcription languages");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <SettingsRow
        icon={Languages}
        title="Main language"
        description="Used for live calls, HubSpot recordings, uploads and WhatsApp."
      >
        <Select value={primary} disabled={saving} onValueChange={(next) => void save(next, extras.filter((c) => c !== next))}>
          <SelectTrigger size="sm" className="w-auto min-w-32" aria-label="Main language">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OPTIONS.map((opt) => (
              <SelectItem key={opt.code} value={opt.code}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </SettingsRow>
      <SettingsRow
        icon={Globe}
        title="Also spoken on calls"
        description="On a live call Vocify hears which language each side speaks and switches to it."
        below={
          <div className="flex flex-wrap gap-2">
            {OPTIONS.filter((opt) => opt.code !== primary).map((opt) => (
              <Toggle
                key={opt.code}
                pressed={extras.includes(opt.code)}
                disabled={saving}
                onPressedChange={(pressed) =>
                  void save(primary, pressed ? [...extras, opt.code] : extras.filter((c) => c !== opt.code))
                }
                variant="chip"
                size="sm"
                aria-label={opt.label}
              >
                {opt.label}
              </Toggle>
            ))}
          </div>
        }
      />
    </>
  );
};
