import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { isManagerRole } from "@/lib/nav";
import HeadOfSalesTeamPage from "./HeadOfSalesTeamPage";
import TeamInsightsPage from "./TeamInsightsPage";

/** Equipo: the Head of Sales gets their table; a member keeps TeamInsightsPage (its own
 * Lista 4 rules: read-only with visibility=team, otherwise redirected to Coach). */
export function InsightsRoute() {
  const { user } = useAuth();
  return isManagerRole(user?.company?.role) ? <HeadOfSalesTeamPage /> : <TeamInsightsPage />;
}

/** Head of Sales-only pages send anyone else home. */
export function ManagerOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && !isManagerRole(user.company?.role)) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
