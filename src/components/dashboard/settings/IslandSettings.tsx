import { useEffect, useState } from "react";
import { PanelRight, PanelTop, SunMoon } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsRow, SettingsSection } from "@/components/ui/settings-card";
import { Switch } from "@/components/ui/switch";
import { getDesktopBridge, type IslandAppearance, type IslandPlacement, type IslandState } from "@/lib/desktop-host";
import { useLanguage } from "@/lib/i18n";

/**
 * The island's appearance, where it sits and whether it shows, on this computer. Only inside the desktop app, and each row
 * only where the app offers that setting (its setter exists and `get()` reports its value): the Mac app and the Electron
 * app offer different ones.
 */
export const IslandSettings = () => {
  const { t } = useLanguage();
  const island = getDesktopBridge()?.island;
  const [state, setState] = useState<IslandState | null>(null);

  useEffect(() => {
    void island?.get().then(setState);
  }, [island]);
  // A setter may answer with only the setting it changed: it is merged into what is known.
  const merge = (next: IslandState) => setState((current) => ({ ...current, ...next }));

  const appearance = island?.setAppearance && state?.appearance ? state.appearance : null;
  const placement = island?.setPlacement && state?.placement ? state.placement : null;
  const visible = island?.setVisible && typeof state?.visible === "boolean" ? state.visible : null;
  if (!island || !state || (!appearance && !placement && visible === null)) return null;

  const appearances: { value: IslandAppearance; label: string }[] = [
    { value: "auto", label: t.product.islandAppearanceAuto },
    { value: "light", label: t.product.islandAppearanceLight },
    { value: "dark", label: t.product.islandAppearanceDark },
  ];
  const placements: { value: IslandPlacement; label: string }[] = [
    { value: "notch", label: t.product.islandPlacementNotch },
    { value: "side", label: t.product.islandPlacementSide },
  ];

  return (
    <SettingsSection label={t.product.settingsSectionIsland}>
      {appearance ? (
        <SettingsRow icon={SunMoon} title={t.product.islandAppearanceTitle} description={t.product.islandAppearanceHelper}>
          <Select value={appearance} onValueChange={(value) => void island.setAppearance?.(value as IslandAppearance).then(merge)}>
            <SelectTrigger variant="chip" aria-label={t.product.islandAppearanceTitle}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {appearances.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingsRow>
      ) : null}
      {placement ? (
        <SettingsRow icon={PanelRight} title={t.product.islandPlacementTitle} description={t.product.islandPlacementHelper}>
          <Select value={placement} onValueChange={(value) => void island.setPlacement?.(value as IslandPlacement).then(merge)}>
            <SelectTrigger variant="chip" aria-label={t.product.islandPlacementTitle}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {placements.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingsRow>
      ) : null}
      {visible !== null ? (
        <SettingsRow icon={PanelTop} title={t.product.islandShowTitle} description={t.product.islandShowHelper}>
          <Switch
            checked={visible}
            onCheckedChange={(on) => void island.setVisible?.(on).then(merge)}
            aria-label={t.product.islandShowTitle}
          />
        </SettingsRow>
      ) : null}
    </SettingsSection>
  );
};
