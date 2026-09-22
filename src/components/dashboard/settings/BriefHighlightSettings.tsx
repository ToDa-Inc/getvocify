import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  briefPreferenceKeys,
  briefPreferencesApi,
  type BriefHighlightMode,
  type BriefPreference,
} from "@/lib/api/brief-preferences";

const OPTIONS: { mode: BriefHighlightMode; label: string }[] = [
  { mode: "immediate", label: "Inmediato" },
  { mode: "deferred", label: "Aplazado 30 minutos" },
  { mode: "end_of_day", label: "Al final del día (18:00)" },
];

export const BriefHighlightSettings = () => {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: briefPreferenceKeys.current(),
    queryFn: () => briefPreferencesApi.get(),
  });
  const [selected, setSelected] = useState<BriefHighlightMode>("immediate");

  useEffect(() => {
    if (data?.highlight_mode) {
      setSelected(data.highlight_mode);
    }
  }, [data?.highlight_mode]);

  const save = useMutation({
    mutationFn: (mode: BriefHighlightMode) => briefPreferencesApi.put({ highlight_mode: mode }),
    onSuccess: (updated: BriefPreference) => {
      queryClient.setQueryData(briefPreferenceKeys.current(), updated);
      setSelected(updated.highlight_mode);
      toast.success("Preferencia de resumen guardada");
    },
    onError: () => {
      toast.error("No se pudo guardar la preferencia");
    },
  });

  const dirty = data != null && selected !== data.highlight_mode;

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <VocifySpinner size={24} />
      </div>
    );
  }

  if (isError) {
    return (
      <p className="text-sm text-muted-foreground">
        No se pudo cargar la preferencia. Inténtalo de nuevo más tarde.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>Resumen posterior</h3>
        <p className="text-xs text-muted-foreground mt-1">
          El resumen se genera en cuanto termina la interacción. Elige cuándo quieres que te lo
          destaquemos.
        </p>
      </div>

      <div className="space-y-2" role="radiogroup" aria-label="Cuándo destacar el resumen">
        {OPTIONS.map((opt) => {
          const on = selected === opt.mode;
          return (
            <button
              key={opt.mode}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setSelected(opt.mode)}
              className={`w-full rounded-2xl border px-4 py-3 text-left text-sm font-medium transition-colors ${
                on
                  ? "border-beige bg-beige/10 text-foreground"
                  : "border-border/40 bg-secondary/5 hover:bg-secondary/10"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      <div className="flex justify-end">
        <Button
          onClick={() => save.mutate(selected)}
          disabled={!dirty || save.isPending}
          className="rounded-full bg-beige text-cream px-6 text-[10px] font-medium"
        >
          {save.isPending ? (
            <>
              <VocifySpinner size={12} />
              Guardando…
            </>
          ) : (
            "Guardar"
          )}
        </Button>
      </div>
    </div>
  );
};
