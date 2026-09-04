import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { authApi } from "@/features/auth";

export const ProductOfferSettings = () => {
  const [value, setValue] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const user = await authApi.me();
        if (!cancelled) setValue(user.productContext || "");
      } catch (error) {
        console.error("Failed to load product context", error);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = async () => {
    try {
      setIsSaving(true);
      await authApi.updateProfile({ productContext: value });
      toast.success("Product context saved");
    } catch {
      toast.error("Could not save product context");
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
    <div className="space-y-4">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>Product & offer</h3>
        <p className="text-xs text-muted-foreground mt-1">
            What you sell, who it is for, and proof points. Used as reference when extracting
            call notes — it is not copied into CRM summaries. Any team can put their own offer here.
        </p>
      </div>
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={8}
        maxLength={8000}
        className="text-sm rounded-2xl"
        placeholder="Product, ICP, what you do not sell, proof points…"
      />
      <div className="flex justify-end">
        <Button
          onClick={handleSave}
          disabled={isSaving}
          className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
        >
          {isSaving ? "Saving…" : "Save offer"}
        </Button>
      </div>
    </div>
  );
};
