import { Navigate, useSearchParams } from "react-router-dom";

/** Integrations now live on Settings → CRM. Keep query strings for OAuth returns. */
const IntegrationsPage = () => {
  const [params] = useSearchParams();
  const q = params.toString();
  return <Navigate to={q ? `/dashboard/settings?${q}` : "/dashboard/settings"} replace />;
};

export default IntegrationsPage;
