import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { BriefHighlightSettings } from "@/components/dashboard/settings/BriefHighlightSettings";
import { FollowupSuggestSettings } from "@/components/dashboard/settings/FollowupSuggestSettings";
import { IslandSettings } from "@/components/dashboard/settings/IslandSettings";
import { RecordShortcutSettings } from "@/components/dashboard/settings/RecordShortcutSettings";
import { ReportPreferencesSettings } from "@/components/dashboard/settings/ReportPreferencesSettings";
import { TranscriptionLanguageSettings } from "@/components/dashboard/settings/TranscriptionLanguageSettings";
import { WritingSamplesSettings } from "@/components/dashboard/settings/WritingSamplesSettings";
import { UserGlossary } from "@/components/dashboard/glossary/UserGlossary";
import { SettingsSection } from "@/components/ui/settings-card";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { isManagerRole } from "@/lib/nav";

/**
 * Everyone's own preferences in one scrolling page (Granola's Preferences): the call languages and the shared
 * glossary, a rep's after-call summary and follow-up, the reports, and what this computer's app offers.
 */
const PreferencesSection = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const { hash } = useLocation();
  const isManager = isManagerRole(user?.company?.role);
  const canManage = user?.company?.role === "owner" || user?.company?.role === "admin";

  // A link to one section (#report-preferences, from a report).
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [hash]);

  return (
    <div className="mx-auto max-w-[680px] space-y-8">
      <SettingsSection label={t.product.settingsSectionLanguage}>
        <TranscriptionLanguageSettings />
        <div className="py-4">
          <UserGlossary readOnly={!canManage} />
        </div>
      </SettingsSection>

      {/* The Head of Sales sets none of these: they are a rep's own summary, follow-up and writing style. */}
      {!isManager && (
        <SettingsSection label={t.product.settingsSectionSummaries}>
          <BriefHighlightSettings />
          <FollowupSuggestSettings />
          <WritingSamplesSettings />
        </SettingsSection>
      )}

      <ReportPreferencesSettings />
      <RecordShortcutSettings />
      <IslandSettings />
    </div>
  );
};

export default PreferencesSection;
