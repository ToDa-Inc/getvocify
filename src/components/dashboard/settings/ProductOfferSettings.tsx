import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { toast } from "sonner";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useAuth } from "@/features/auth";
import { authApi, authKeys } from "@/features/auth/api";
import type { User } from "@/features/auth/types";
import { useLanguage } from "@/lib/i18n";

export const ProductOfferSettings = ({ readOnly = false }: { readOnly?: boolean }) => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [value, setValue] = useState(user?.productContext ?? "");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setValue(user?.productContext ?? "");
  }, [user?.productContext]);

  const handleSave = async () => {
    try {
      setIsSaving(true);
      const updated = await authApi.updateProfile({ productContext: value });
      queryClient.setQueryData<User>(authKeys.me(), updated);
      toast.success(t.product.offerSavedToast);
    } catch {
      toast.error(t.product.offerSaveFailedToast);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.offerSectionTitle}</h3>
        <p className="text-xs text-muted-foreground mt-1">{t.product.offerSectionHelper}</p>
      </div>
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={8}
        maxLength={8000}
        readOnly={readOnly}
        disabled={readOnly}
        className="text-sm rounded-2xl"
        placeholder={t.product.offerPlaceholder}
      />
      {!readOnly && (
      <div className="flex justify-end">
        <Button
          onClick={handleSave}
          disabled={isSaving}
          className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
        >
          {isSaving ? (
            <>
              <VocifySpinner size={12} />
              {t.product.offerSaving}
            </>
          ) : (
            t.product.offerSaveButton
          )}
        </Button>
      </div>
      )}
    </div>
  );
};
