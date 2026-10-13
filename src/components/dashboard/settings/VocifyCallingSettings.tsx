import { Switch } from "@/components/ui/switch";
import { useDesktopCalling } from "@/features/desktop/useDesktopCalling";
import { desktopPlatform, getDesktopBridge } from "@/lib/desktop-host";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/** Where the island's Call goes on this computer: through Vocify, or to the rep's own phone (desktop app only). With
 * the phone, the one setup this computer may still need, and a click to where it is done. */
export const VocifyCallingSettings = () => {
  const { t } = useLanguage();
  const { calling, setOnPhone } = useDesktopCalling();
  if (!calling) return null;
  const isMac = desktopPlatform() === "darwin";
  const helper = !calling.onPhone
    ? t.product.vocifyCallingOn
    : !calling.phoneApp
      ? t.product.vocifyCallingNoApp
      : isMac
        ? t.product.vocifyCallingOffMac
        : t.product.vocifyCallingOff.replace("{app}", calling.phoneApp);
  // A Mac always has FaceTime, but not whether the iPhone lets it call; Windows only needs an app for TEL links.
  const setup = !calling.onPhone
    ? null
    : isMac
      ? { line: t.product.vocifyCallingSetupMac, button: t.product.vocifyCallingOpenFaceTime }
      : !calling.phoneApp
        ? { line: null, button: t.product.vocifyCallingOpenDefaultApps }
        : null;
  const openSetup = getDesktopBridge()?.calling?.setup;
  return (
    <div className="flex items-start justify-between gap-6">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.vocifyCallingHeading}</h3>
        <p className="text-xs text-muted-foreground mt-1">{helper}</p>
        {setup?.line ? <p className="text-xs text-muted-foreground mt-1">{setup.line}</p> : null}
        {setup && openSetup ? (
          <button type="button" className="mt-2 text-xs text-beige hover:underline" onClick={() => void openSetup()}>
            {setup.button}
          </button>
        ) : null}
      </div>
      <Switch
        checked={!calling.onPhone}
        onCheckedChange={(vocify) => setOnPhone(!vocify)}
        aria-label={t.product.vocifyCallingHeading}
      />
    </div>
  );
};
