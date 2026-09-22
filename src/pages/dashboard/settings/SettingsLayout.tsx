import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/features/auth";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { companyIsPaywalled } from "@/lib/billing-access";
import { crmApi, crmKeys, SESSION_QUERY_STALE_MS } from "@/lib/api/crm";
import { loadHubSpotSetup } from "@/lib/api/hubspot-setup";
import { loadSalesforceSetup } from "@/lib/api/salesforce-setup";
import { callKeys, callsApi } from "@/features/calls/api";

const SECTIONS = [
  { to: "/dashboard/settings", label: "CRM", end: true },
  { to: "/dashboard/settings/calling", label: "Calling" },
  { to: "/dashboard/settings/offer", label: "Offer" },
  { to: "/dashboard/settings/glossary", label: "Glossary" },
  { to: "/dashboard/settings/playbooks", label: "Proceso" },
  { to: "/dashboard/settings/team", label: "Team" },
  { to: "/dashboard/settings/usage", label: "Usage" },
  { to: "/dashboard/settings/billing", label: "Billing" },
] as const;

const navClass = ({ isActive }: { isActive: boolean }) =>
  `shrink-0 lg:w-full lg:text-left ${THEME_TOKENS.interaction.navPill} ${
    isActive ? THEME_TOKENS.interaction.navPillActive : THEME_TOKENS.interaction.navPillIdle
  }`;

const SettingsLayout = () => {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const paywalled = companyIsPaywalled(user?.company);

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
    <div className={`max-w-5xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="mb-6">
        <h1 className={THEME_TOKENS.typography.pageTitle}>{paywalled ? "Billing" : "Settings"}</h1>
      </div>

      <div className={`lg:items-start ${paywalled ? "" : "lg:grid lg:grid-cols-[11.5rem_minmax(0,1fr)] lg:gap-10"}`}>
        {!paywalled && (
          <nav
            aria-label="Settings sections"
            className="sticky top-0 z-10 flex gap-1 overflow-x-auto bg-background py-3 -mx-1 px-1 mb-6 lg:mb-0 lg:flex-col lg:overflow-visible lg:py-0"
          >
            {SECTIONS.map((section) => (
              <NavLink
                key={section.to}
                to={section.to}
                end={"end" in section ? section.end : false}
                className={navClass}
              >
                {section.label}
              </NavLink>
            ))}
          </nav>
        )}

        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </div>
  );
};

export default SettingsLayout;
