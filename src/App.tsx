import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import PrivacyPage from "./pages/PrivacyPage";
import AboutPage from "./pages/AboutPage";
import BlogPage from "./pages/BlogPage";
import TermsPage from "./pages/TermsPage";
import DocsPage from "./pages/DocsPage";
import SupportPage from "./pages/SupportPage";
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
import ObjectionCopilotPage from "./pages/dashboard/ObjectionCopilotPage";
import AdminLayout from "./components/admin/AdminLayout";
import AdminAccountsPage from "./pages/admin/AdminAccountsPage";
import AdminAccountDetailPage from "./pages/admin/AdminAccountDetailPage";

import { LanguageProvider } from "@/lib/i18n";
import { AuthProvider, useAuth } from "@/features/auth";
import { Navigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { isLandingDomain, isLandingPath, APP_URL } from "@/lib/app-url";
import { VocifyLoader } from "@/components/ui/vocify-loader";

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
        <VocifyLoader size="md" />
      </div>
    );
  }
  return null;
};

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated, isLoading, hasStoredSession, restoreSession } = useAuth();
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream">
        <VocifyLoader size="md" />
      </div>
    );
  }

  if (!hasStoredSession) {
    return <Navigate to="/login" replace />;
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-cream px-6">
        <VocifyLoader size="md" label="Restoring your session" />
        <button
          type="button"
          className="text-[10px] font-black uppercase tracking-widest text-beige hover:underline"
          onClick={() => restoreSession()}
        >
          Try again
        </button>
      </div>
    );
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
            <Route path="/en" element={<Index />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/blog" element={<BlogPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/docs" element={<DocsPage />} />
            <Route path="/support" element={<SupportPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<AdminAccountsPage />} />
              <Route path="accounts/:userId" element={<AdminAccountDetailPage />} />
            </Route>
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
              <Route path="copilot" element={<ObjectionCopilotPage />} />
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
