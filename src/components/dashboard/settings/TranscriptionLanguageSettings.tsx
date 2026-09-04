import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { authApi } from "@/features/auth";

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

export const TranscriptionLanguageSettings = () => {
  const [primary, setPrimary] = useState("es");
  const [extras, setExtras] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const user = await authApi.me();
        const langs = user.sttLanguages?.length ? user.sttLanguages : ["es"];
        if (!cancelled) {
          setPrimary(langs[0] || "es");
          setExtras(langs.slice(1));
        }
      } catch (error) {
        console.error("Failed to load transcription languages", error);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleExtra = (code: string) => {
    setExtras((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  };

  const handleSave = async () => {
    try {
      setIsSaving(true);
      const updated = await authApi.updateProfile({
        sttLanguages: packLanguages(primary, extras),
      });
      const langs = updated.sttLanguages?.length ? updated.sttLanguages : ["es"];
      setPrimary(langs[0] || "es");
      setExtras(langs.slice(1));
      toast.success("Transcription languages saved");
    } catch {
      toast.error("Could not save transcription languages");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin text-beige" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>Call languages</h3>
        <p className="text-xs text-muted-foreground mt-1">
            Main language for HubSpot recordings, uploads, and WhatsApp. Add others only if
            those calls mix languages.
        </p>
      </div>

      <div className="space-y-2">
        <label className={THEME_TOKENS.typography.capsLabel}>Main language</label>
        <select
          value={primary}
          onChange={(e) => {
            const next = e.target.value;
            setPrimary(next);
            setExtras((prev) => prev.filter((c) => c !== next));
          }}
          className="h-11 w-full rounded-full border border-border/40 bg-secondary/5 px-6 text-sm font-bold"
        >
          {OPTIONS.map((opt) => (
            <option key={opt.code} value={opt.code}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <p className={THEME_TOKENS.typography.capsLabel}>Also spoken on calls</p>
        <div className="flex flex-wrap gap-2">
          {OPTIONS.filter((opt) => opt.code !== primary).map((opt) => {
            const on = extras.includes(opt.code);
            return (
              <button
                key={opt.code}
                type="button"
                onClick={() => toggleExtra(opt.code)}
                className={`rounded-full px-4 h-9 text-xs font-medium border transition-colors ${
                  on
                    ? "bg-beige text-cream border-beige"
                    : "bg-secondary/5 text-foreground border-border/40 hover:bg-secondary/10"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex justify-end">
        <Button
          onClick={handleSave}
          disabled={isSaving}
          className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
        >
          {isSaving ? "Saving…" : "Save languages"}
        </Button>
      </div>
    </div>
  );
};
