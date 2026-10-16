import { Fragment, useEffect, useMemo } from "react";
import {
  BarChart3, Bot, CalendarDays, CreditCard, Drama, Monitor, Package, Phone, Plug, SlidersHorizontal, Users,
  type LucideIcon,
} from "lucide-react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { useLanguage } from "@/lib/i18n";
import { isDesktopHost } from "@/lib/desktop-host";
import { isManagerRole } from "@/lib/nav";
import {
  SETTINGS_ROOT,
  firstAllowedSettingsPath,
  isSettingsPathAllowed,
  visibleSettingsTabs,
  type SettingsTabId,
} from "@/lib/settings-nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { companyIsPaywalled } from "@/lib/billing-access";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS } from "@/lib/api/crm";
import { loadHubSpotSetup } from "@/lib/api/hubspot-setup";
import { loadSalesforceSetup } from "@/lib/api/salesforce-setup";
import { callKeys, callsApi } from "@/features/calls/api";

const TAB_ICONS: Record<SettingsTabId, LucideIcon> = {
  preferences: SlidersHorizontal,
  calling: Phone,
  calendar: CalendarDays,
  agents: Bot,
  system: Monitor,
  usage: BarChart3,
  crm: Plug,
  offer: Package,
  team: Users,
  billing: CreditCard,
  demo: Drama,
};

const navClass = ({ isActive }: { isActive: boolean }) =>
  `flex shrink-0 items-center gap-2.5 whitespace-nowrap lg:w-full lg:text-left ${THEME_TOKENS.interaction.navPill} ${
    isActive ? THEME_TOKENS.interaction.navPillActive : THEME_TOKENS.interaction.navPillIdle
  }`;

const SettingsLayout = () => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { t } = useLanguage();
  const location = useLocation();
  const paywalled = companyIsPaywalled(user?.company);
  // Item 2 / Lista 4 E6: a rep (member) sees their own Preferences, Calling, Agents and Usage; the Head of
  // Sales (owner/admin) sees everything, including the company-wide sections (CRM, Offer, Team, Billing).
  const isManager = isManagerRole(user?.company?.role);
  const features = useMemo(() => user?.company?.features ?? [], [user?.company?.features]);

  // The desktop app adds System: this computer's permissions, audio check and shortcut.
  const host = useMemo(() => ({ desktop: isDesktopHost() }), []);
  const sections = useMemo(() => visibleSettingsTabs(isManager, features, host), [isManager, features, host]);
  // A member who navigates straight to a manager-only settings URL (bookmark, typed
  // link) lands on their first allowed tab instead. Skip while `user` hasn't loaded
  // yet, so a manager never flashes to Calling before their role is known.
  // The bare /settings is not a tab: its index route sends everyone on (a CRM's OAuth return keeps its query).
  const needsRedirect =
    Boolean(user) &&
    !paywalled &&
    location.pathname !== SETTINGS_ROOT &&
    !isSettingsPathAllowed(location.pathname, isManager, features, host);

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
              {sections.map((section, index) => {
                const Icon = TAB_ICONS[section.id];
                const startsWorkspace = section.group === "workspace" && sections[index - 1]?.group !== "workspace";
                return (
                  <Fragment key={section.to}>
                    {startsWorkspace ? (
                      <p className={`hidden px-3.5 pb-1 pt-5 lg:block ${THEME_TOKENS.typography.capsLabel}`}>
                        {t.product.settingsGroupWorkspace}
                      </p>
                    ) : null}
                    <NavLink to={section.to} className={navClass}>
                      <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                      {t.product[section.labelKey]}
                    </NavLink>
                  </Fragment>
                );
              })}
            </nav>
          </div>
        )}

        <div className="min-w-0">
          {needsRedirect ? <Navigate to={firstAllowedSettingsPath(isManager, features, host)} replace /> : <Outlet />}
        </div>
      </div>
    </div>
  );
};

export default SettingsLayout;
