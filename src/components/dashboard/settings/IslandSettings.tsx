import { useEffect, useState } from "react";
import { PanelTop, SunMoon } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsRow, SettingsSection } from "@/components/ui/settings-card";
import { Switch } from "@/components/ui/switch";
import { getDesktopBridge, type IslandAppearance, type IslandState } from "@/lib/desktop-host";
import { useLanguage } from "@/lib/i18n";

/** The island's appearance and whether it shows, on this computer. Only inside the desktop app, and only where it offers them. */
export const IslandSettings = () => {
  const { t } = useLanguage();
  const island = getDesktopBridge()?.island;
  const [state, setState] = useState<IslandState | null>(null);

  useEffect(() => {
    void island?.get().then(setState);
  }, [island]);

  if (!island || !state) return null;

  const appearances: { value: IslandAppearance; label: string }[] = [
    { value: "auto", label: t.product.islandAppearanceAuto },
    { value: "light", label: t.product.islandAppearanceLight },
    { value: "dark", label: t.product.islandAppearanceDark },
  ];

  return (
    <SettingsSection label={t.product.settingsSectionIsland}>
      <SettingsRow icon={SunMoon} title={t.product.islandAppearanceTitle} description={t.product.islandAppearanceHelper}>
        <Select value={state.appearance} onValueChange={(value) => void island.setAppearance(value as IslandAppearance).then(setState)}>
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
      <SettingsRow icon={PanelTop} title={t.product.islandShowTitle} description={t.product.islandShowHelper}>
        <Switch
          checked={state.visible}
          onCheckedChange={(visible) => void island.setVisible(visible).then(setState)}
          aria-label={t.product.islandShowTitle}
        />
      </SettingsRow>
    </SettingsSection>
  );
};
