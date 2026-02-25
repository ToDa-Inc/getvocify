import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import LoginPage from "./pages/auth/LoginPage";
import SignupPage from "./pages/auth/SignupPage";
import DashboardLayout from "./components/dashboard/DashboardLayout";
import DashboardHome from "./pages/dashboard/DashboardHome";
import RecordPage from "./pages/dashboard/RecordPage";
import MemosPage from "./pages/dashboard/MemosPage";
import MemoDetail from "./pages/dashboard/MemoDetail";
import IntegrationsPage from "./pages/dashboard/IntegrationsPage";
import SettingsPage from "./pages/dashboard/SettingsPage";
import ProfilePage from "./pages/dashboard/ProfilePage";
import UsagePage from "./pages/dashboard/UsagePage";

import { LanguageProvider } from "@/lib/i18n";
import { AuthProvider, useAuth } from "@/features/auth";
import { Navigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { isLandingDomain, isLandingPath, APP_URL } from "@/lib/app-url";

/** Redirects getvocify.com/login, /dashboard, etc. → app.getvocify.com */
const LandingDomainRedirect = () => {
  const location = useLocation();
  const needsRedirect = isLandingDomain() && !isLandingPath(location.pathname);

  useEffect(() => {
    if (needsRedirect) {
      window.location.replace(APP_URL + location.pathname + location.search);
    }
  }, [needsRedirect, location.pathname, location.search]);

  if (needsRedirect) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream">
        <div className="w-8 h-8 border-4 border-beige border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  return null;
};

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated, isLoading } = useAuth();
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream">
        <div className="w-8 h-8 border-4 border-beige border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  
  return <>{children}</>;
};

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <LanguageProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <LandingDomainRedirect />
          <Routes>
            <Route path="/" element={<Index />} />
            <Route path="/es" element={<Index />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/dashboard" element={
              <ProtectedRoute>
                <DashboardLayout />
              </ProtectedRoute>
            }>
              <Route index element={<DashboardHome />} />
              <Route path="record" element={<RecordPage />} />
              <Route path="memos" element={<MemosPage />} />
              <Route path="memos/:id" element={<MemoDetail />} />
              <Route path="integrations" element={<IntegrationsPage />} />
              <Route path="profile" element={<ProfilePage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="usage" element={<UsagePage />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </LanguageProvider>
  </AuthProvider>
</QueryClientProvider>
);

export default App;
