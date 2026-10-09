import { Navigate } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { InicioPage } from "@/features/home/components/InicioPage";

/** Inicio for every role (the paywall redirect lives in DashboardLayout). The full Hoy is /dashboard/today. */
const DashboardHome = () => {
  const { user } = useAuth();
  // T9: send an owner/admin who hasn't finished onboarding to the wizard first.
  if (user?.company?.needsOnboarding) return <Navigate to="/dashboard/onboarding" replace />;
  return <InicioPage />;
};

export default DashboardHome;
