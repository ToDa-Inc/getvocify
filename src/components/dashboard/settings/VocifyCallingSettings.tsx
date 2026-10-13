import { Switch } from "@/components/ui/switch";
import { useDesktopCalling } from "@/features/desktop/useDesktopCalling";
import { desktopPlatform } from "@/lib/desktop-host";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** Where the island's Call goes on this computer: through Vocify, or to the rep's own phone (desktop app only). */
export const VocifyCallingSettings = () => {
  const { t } = useLanguage();
  const { calling, setOnPhone } = useDesktopCalling();
  if (!calling) return null;
  const helper = !calling.onPhone
    ? t.product.vocifyCallingOn
    : !calling.phoneApp
      ? t.product.vocifyCallingNoApp
      : desktopPlatform() === "darwin"
        ? t.product.vocifyCallingOffMac
        : t.product.vocifyCallingOff.replace("{app}", calling.phoneApp);
  return (
    <div className="flex items-start justify-between gap-6">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.vocifyCallingHeading}</h3>
        <p className="text-xs text-muted-foreground mt-1">{helper}</p>
      </div>
      <Switch
        checked={!calling.onPhone}
        onCheckedChange={(vocify) => setOnPhone(!vocify)}
        aria-label={t.product.vocifyCallingHeading}
      />
    </div>
  );
};
