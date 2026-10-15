import { Phone } from "lucide-react";
import { SettingsRow } from "@/components/ui/settings-card";
import { Switch } from "@/components/ui/switch";
import { useDesktopCalling } from "@/features/desktop/useDesktopCalling";
import { desktopPlatform, getDesktopBridge } from "@/lib/desktop-host";
import { useLanguage } from "@/lib/i18n";

/** Where the island's Call goes on this computer: through Vocify, or to the rep's own phone (desktop app only). With
 * the phone, the one setup this computer may still need, and a click to where it is done. */
export const VocifyCallingSettings = () => {
  const { t } = useLanguage();
  const { calling, setOnPhone } = useDesktopCalling();
  if (!calling) return null;
  // FaceTime's wording only where FaceTime places the call: the calling app is the fact, the platform only a fallback.
  const isMac = calling.phoneApp ? calling.phoneApp === "FaceTime" : desktopPlatform() === "darwin";
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
  const hasExtra = Boolean(setup?.line || mic || (setup && openSetup) || (mic?.button && openMic));
  return (
    <SettingsRow
      icon={Phone}
      title={t.product.vocifyCallingHeading}
      description={helper}
      below={
        hasExtra ? (
          <div className="space-y-1">
            {setup?.line ? <p className="text-xs text-muted-foreground">{setup.line}</p> : null}
            {mic ? <p className="text-xs text-muted-foreground">{mic.line}</p> : null}
            <div className="flex gap-4 pt-1">
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
        ) : null
      }
    >
      <Switch
        checked={!calling.onPhone}
        onCheckedChange={(vocify) => setOnPhone(!vocify)}
        aria-label={t.product.vocifyCallingHeading}
      />
    </SettingsRow>
  );
};
