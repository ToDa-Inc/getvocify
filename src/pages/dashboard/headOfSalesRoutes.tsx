import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { isManagerRole } from "@/lib/nav";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import HeadOfSalesTeamPage from "./HeadOfSalesTeamPage";
import TeamInsightsPage from "./TeamInsightsPage";

/** Role is unknown until `user` loads: show the app's loader rather than a page that may be the wrong one. */
function RouteLoader() {
  return (
    <div className={THEME_TOKENS.interaction.pageLoad}>
      <VocifyLoader size="md" />
    </div>
  );
}

/** Equipo: the Head of Sales gets Resumen and Personas; a member keeps TeamInsightsPage (its own
 * Lista 4 rules: read-only with visibility=team, otherwise redirected to Coach). */
export function InsightsRoute() {
  const { user } = useAuth();
  if (!user) return <RouteLoader />;
  return isManagerRole(user.company?.role) ? <HeadOfSalesTeamPage /> : <TeamInsightsPage />;
}

/** Coaching is the rep's own page; the Head of Sales reads each rep's focus in Equipo. */
export function RepOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!user) return <RouteLoader />;
  if (isManagerRole(user.company?.role)) return <Navigate to="/dashboard/insights" replace />;
  return <>{children}</>;
}
