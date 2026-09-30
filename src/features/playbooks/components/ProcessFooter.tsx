import { Plus } from "@phosphor-icons/react";
import { AddTypeMenu } from "@/features/playbooks/components/AddTypeMenu";
import { linkButton } from "@/features/playbooks/styles";
import { Button } from "@/components/ui/button";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { useLanguage } from "@/lib/i18n";
import type { CatalogType } from "@/lib/playbook-doc";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * The quiet actions on the left ("Añadir desde un documento", "+ Tipo de llamada") and, only
 * when something is pending, the page's one action on the right: "Activar para el equipo".
 */
export function ProcessFooter({
  showAddFromDoc,
  onAddFromDoc,
  addable,
  stages,
  showAddType,
  onTypeAdded,
  pendingCount,
  activating,
  onActivate,
}: {
  showAddFromDoc: boolean;
  onAddFromDoc: () => void;
  addable: CatalogType[];
  stages: { id: string; label: string }[];
  showAddType: boolean;
  onTypeAdded: (key: string) => void;
  pendingCount: number;
  activating: boolean;
  onActivate: () => void;
}) {
  const { t } = useLanguage();
  const copy = t.product.pb2;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/40 py-3">
      <div className="flex flex-wrap items-center gap-1">
        {showAddFromDoc ? (
          <button type="button" className={linkButton} onClick={onAddFromDoc}>
            <Plus size={12} weight="light" />
            {copy.addFromDoc}
          </button>
        ) : null}
        {showAddType ? <AddTypeMenu catalog={addable} stages={stages} onAdded={onTypeAdded} /> : null}
      </div>
      {pendingCount > 0 ? (
        <div className={cn("flex flex-wrap items-center gap-3", THEME_TOKENS.motion.fadeIn)}>
          <span className={cn(THEME_TOKENS.typography.capsLabel, "hidden sm:inline")}>{copy.pendingBar}</span>
          <Button type="button" size="sm" disabled={activating} onClick={onActivate}>
            {activating ? (
              <>
                <VocifySpinner size={12} />
                <span className="ml-1.5">{copy.activating}</span>
              </>
            ) : (
              copy.activate
            )}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
