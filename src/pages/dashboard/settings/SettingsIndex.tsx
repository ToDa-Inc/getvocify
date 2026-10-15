import { useMemo } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { isDesktopHost } from "@/lib/desktop-host";
import { isManagerRole } from "@/lib/nav";
import { firstAllowedSettingsPath } from "@/lib/settings-nav";

/** The bare /dashboard/settings. A CRM's OAuth return lands here with its status in the query, and goes on to the CRM page. */
const SettingsIndex = () => {
  const { search } = useLocation();
  const { user } = useAuth();
  const isManager = isManagerRole(user?.company?.role);
  const features = useMemo(() => user?.company?.features ?? [], [user?.company?.features]);
  if (search) return <Navigate to={`/dashboard/settings/crm${search}`} replace />;
  return <Navigate to={firstAllowedSettingsPath(isManager, features, { desktop: isDesktopHost() })} replace />;
};

export default SettingsIndex;
