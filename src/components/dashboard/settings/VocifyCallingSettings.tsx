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
  const bridgeCalling = getDesktopBridge()?.calling;
  const openSetup = bridgeCalling?.setup;
  // "They can't hear me": the call's microphone is chosen in FaceTime on a Mac, and in Windows' Sound settings.
  const mic = calling.onPhone && calling.phoneApp
    ? isMac
      ? { line: t.product.vocifyCallingMicMac, button: null }
      : { line: t.product.vocifyCallingMicWindows, button: t.product.vocifyCallingOpenSound }
    : null;
  const openMic = bridgeCalling?.micSettings;
  return (
    <div className="flex items-start justify-between gap-6">
      <div>
        <h3 className={THEME_TOKENS.typography.sectionTitle}>{t.product.vocifyCallingHeading}</h3>
        <p className="text-xs text-muted-foreground mt-1">{helper}</p>
        {setup?.line ? <p className="text-xs text-muted-foreground mt-1">{setup.line}</p> : null}
        {mic ? <p className="text-xs text-muted-foreground mt-1">{mic.line}</p> : null}
        <div className="mt-2 flex gap-4">
          {/* On a Mac, Open FaceTime covers both: Calls from iPhone and the call's microphone are set there. */}
          {setup && openSetup ? (
            <button type="button" className="text-xs text-beige hover:underline" onClick={() => void openSetup()}>
              {setup.button}
            </button>
          ) : null}
          {mic?.button && openMic ? (
            <button type="button" className="text-xs text-beige hover:underline" onClick={() => void openMic()}>
              {mic.button}
            </button>
          ) : null}
        </div>
      </div>
      <Switch
        checked={!calling.onPhone}
        onCheckedChange={(vocify) => setOnPhone(!vocify)}
        aria-label={t.product.vocifyCallingHeading}
      />
    </div>
  );
};
