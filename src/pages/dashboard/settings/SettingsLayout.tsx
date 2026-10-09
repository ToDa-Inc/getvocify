import { useEffect, useMemo } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { RecordShortcutSettings } from "@/components/dashboard/settings/RecordShortcutSettings";
import { isManagerRole } from "@/lib/nav";
import { firstAllowedSettingsPath, isSettingsPathAllowed, visibleSettingsTabs } from "@/lib/settings-nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { companyIsPaywalled } from "@/lib/billing-access";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS } from "@/lib/api/crm";
import { loadHubSpotSetup } from "@/lib/api/hubspot-setup";
import { loadSalesforceSetup } from "@/lib/api/salesforce-setup";
import { callKeys, callsApi } from "@/features/calls/api";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `shrink-0 whitespace-nowrap lg:w-full lg:text-left ${THEME_TOKENS.interaction.navPill} ${
    isActive ? THEME_TOKENS.interaction.navPillActive : THEME_TOKENS.interaction.navPillIdle
  }`;

const SettingsLayout = () => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { t } = useLanguage();
  const location = useLocation();
  const paywalled = companyIsPaywalled(user?.company);
  // Item 2 / Lista 4 E6: a rep (member) sees Calling, the shared Glossary (read-only)
  // and their own Usage; the Head of Sales (owner/admin) sees everything, including the
  // company-wide sections (CRM, Offer, Brief, Team, Playbooks, Billing).
  const isManager = isManagerRole(user?.company?.role);
  const features = useMemo(() => user?.company?.features ?? [], [user?.company?.features]);

  const sections = useMemo(() => visibleSettingsTabs(isManager, features), [isManager, features]);
  // A member who navigates straight to a manager-only settings URL (bookmark, typed
  // link) lands on their first allowed tab instead. Skip while `user` hasn't loaded
  // yet, so a manager never flashes to Calling before their role is known.
  const needsRedirect =
    Boolean(user) && !paywalled && !isSettingsPathAllowed(location.pathname, isManager, features);

  useEffect(() => {
    if (paywalled) return;
    void queryClient.prefetchQuery({
      queryKey: callKeys.config(),
      queryFn: () => callsApi.getConfig(),
      staleTime: SESSION_QUERY_STALE_MS,
    });

    void queryClient
      .prefetchQuery({
        queryKey: crmKeys.connections(),
        queryFn: async () => {
          const { connections } = await crmApi.listConnections();
          return (connections || []).filter((c) => c.status === "connected");
        },
        staleTime: SESSION_QUERY_STALE_MS,
      })
      .then((connections) => {
        if (connections?.some((c) => c.provider === "hubspot")) {
          void queryClient.prefetchQuery({
            queryKey: crmKeys.hubspotSetup(),
            queryFn: () => loadHubSpotSetup(false),
            staleTime: SESSION_QUERY_STALE_MS,
          });
        }
        if (connections?.some((c) => c.provider === "salesforce")) {
          void queryClient.prefetchQuery({
            queryKey: crmKeys.salesforceSetup(),
            queryFn: loadSalesforceSetup,
            staleTime: SESSION_QUERY_STALE_MS,
          });
        }
      });
  }, [queryClient, paywalled]);

  return (
    <div className={`max-w-[1400px] mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="mb-6">
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          {paywalled ? t.product.settingsPageTitleBilling : t.product.settingsPageTitle}
        </h1>
      </div>

      <div className={`lg:items-start ${paywalled ? "" : "lg:grid lg:grid-cols-[max-content_minmax(0,1fr)] lg:gap-10"}`}>
        {!paywalled && (
          <div>
            <nav
              aria-label={t.product.settingsNavAria}
              className="sticky top-0 z-10 flex gap-1 overflow-x-auto bg-background py-3 -mx-1 px-1 mb-6 lg:mb-0 lg:flex-col lg:overflow-visible lg:py-0"
            >
              {sections.map((section) => (
                <NavLink
                  key={section.to}
                  to={section.to}
                  end={"end" in section ? section.end : false}
                  className={navClass}
                >
                  {t.product[section.labelKey]}
                </NavLink>
              ))}
            </nav>
            <RecordShortcutSettings />
          </div>
        )}

        <div className="min-w-0">
          {needsRedirect ? <Navigate to={firstAllowedSettingsPath(isManager, features)} replace /> : <Outlet />}
        </div>
      </div>
    </div>
  );
};

export default SettingsLayout;
