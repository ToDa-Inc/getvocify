import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Outlet, Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { getUserDisplayName, getUserInitials } from "@/features/auth/types";
import {
  Home,
  Mic,
  Settings,
  Menu,
  X,
  Headphones,
  Phone,
  LogOut,
  MessageCircle,
  Bell,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { IconAction } from "@/components/ui/icon-action";
import Logo from "@/components/Logo";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { bellCount } from "@/lib/report-snapshot";
import { api } from "@/shared/lib/api-client";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import ImpersonationBanner from "@/components/admin/ImpersonationBanner";
import { getImpersonation, returnToAdmin } from "@/lib/admin-impersonation";
import { FloatingDialer } from "@/components/dashboard/calling/FloatingDialer";
import { DialerFocusProvider, useDialerFocus } from "@/features/calling/DialerFocusProvider";
import { CALL_STATES, isInCall, type CallState } from "@/lib/dial-target";
import { companyCanUseDialer, companyIsPaywalled } from "@/lib/billing-access";
import AskPanel from "@/features/ask/components/AskPanel";

const navItems = [
  { icon: Home, labelKey: "navHome" as const, path: "/dashboard" },
  { icon: Mic, labelKey: "navMemos" as const, path: "/dashboard/memos" },
  { icon: Headphones, labelKey: "navCopilot" as const, path: "/dashboard/copilot", beta: true },
  { icon: MessageCircle, labelKey: "navAsk" as const, path: "/dashboard/ask" },
  { icon: Users, labelKey: "navInsights" as const, path: "/dashboard/insights", managers: true },
  { icon: Settings, labelKey: "navSettings" as const, path: "/dashboard/settings" },
];

function ReportBell() {
  const { t } = useLanguage();
  const query = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ unread: number | null; items: { id: string; report_id: string }[] }>("/notifications"),
  });
  const count = bellCount(query.isSuccess ? query.data.unread : null);
  const reportId = query.data?.items[0]?.report_id;
  return (
    <Link
      to={reportId ? `/dashboard/reports/${reportId}` : "/dashboard"}
      aria-label={count ? t.product.reportUnread.replace("{count}", String(count)) : t.product.reportsLabel}
      className="relative inline-flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
    >
      <Bell className="h-4 w-4" />
      {count ? (
        <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-beige px-1 text-center text-[10px] text-cream">
          {count}
        </span>
      ) : null}
    </Link>
  );
}

const BILLING_PATH = "/dashboard/settings/billing";

const DashboardLayout = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dialerOpen, setDialerOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [callState, setCallState] = useState<CallState>(CALL_STATES.IDLE);
  const location = useLocation();
  const { t } = useLanguage();
  const { user, logout } = useAuth();
  const impersonating = !!getImpersonation();
  const dialerLive = isInCall(callState);
  const dialerActive = dialerOpen || dialerLive;
  const canManageBilling = user?.company?.role === "owner" || user?.company?.role === "admin";
  const paywalled = companyIsPaywalled(user?.company);

  useEffect(() => {
    const state = location.state as { ask?: boolean } | null;
    if (state?.ask) setAskOpen(true);
  }, [location.state]);
  const showDialer = !paywalled && companyCanUseDialer(user?.company);

  if (paywalled && location.pathname !== BILLING_PATH) {
    return <Navigate to={BILLING_PATH} replace />;
  }

  const isActive = (path: string) => {
    if (path === "/dashboard") {
      return location.pathname === "/dashboard";
    }
    return location.pathname.startsWith(path);
  };

  return (
    <DialerFocusProvider onOpenDialer={() => setDialerOpen(true)}>
    <div className="dashboard-shell h-dvh bg-background flex w-full overflow-hidden">
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-foreground/20 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 bg-background border-r border-border flex flex-col h-screen transform transition-transform duration-150 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
      >
        <div className="px-5 py-6 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <Logo size="sm" />
            <span className="px-1.5 py-px text-[10px] font-medium text-beige bg-beige/10 rounded-md">
              Beta
            </span>
            <ReportBell />
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto">
          {!paywalled && navItems.filter((item) => !("managers" in item && item.managers) || canManageBilling).map((item) => (
            item.path.endsWith("/ask") ? (
            <button
              key={item.path}
              type="button"
              aria-expanded={askOpen}
              onClick={() => {
                setAskOpen((open) => !open);
                setSidebarOpen(false);
              }}
              className={`
                flex w-full items-center gap-3 px-3 py-2 text-[13.5px]
                ${THEME_TOKENS.radius.pill} transition-colors duration-150
                ${askOpen
                  ? THEME_TOKENS.interaction.navPillActive
                  : THEME_TOKENS.interaction.navPillIdle}
              `}
            >
              <item.icon className={`h-4 w-4 ${askOpen ? "opacity-100" : "opacity-70"}`} />
              <span className="flex-1 text-left">{t.product[item.labelKey]}</span>
            </button>
            ) : (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => setSidebarOpen(false)}
              className={`
                flex items-center gap-3 px-3 py-2 text-[13.5px]
                ${THEME_TOKENS.radius.pill} transition-colors duration-150
                ${isActive(item.path)
                  ? THEME_TOKENS.interaction.navPillActive
                  : THEME_TOKENS.interaction.navPillIdle}
              `}
            >
              <item.icon className={`h-4 w-4 ${isActive(item.path) ? "opacity-100" : "opacity-70"}`} />
              <span className="flex-1">{t.product[item.labelKey]}</span>
              {"beta" in item && item.beta && (
                <span className="text-[10px] font-medium text-beige">Beta</span>
              )}
            </Link>
            )
          ))}
          {showDialer && (
            <button
              type="button"
              aria-label={t.product.navCall}
              aria-expanded={dialerOpen}
              onClick={() => {
                setDialerOpen((current) => !current);
                setSidebarOpen(false);
              }}
              className={`
                flex w-full items-center gap-3 px-3 py-2 text-[13.5px]
                ${THEME_TOKENS.radius.pill} transition-colors duration-150
                ${dialerActive
                  ? THEME_TOKENS.interaction.navPillActive
                  : THEME_TOKENS.interaction.navPillIdle}
              `}
            >
              <Phone className={`h-4 w-4 ${dialerActive ? "opacity-100" : "opacity-70"}`} />
              <span className="flex-1 text-left">{t.product.navCall}</span>
              {dialerLive ? (
                <span className="h-1.5 w-1.5 rounded-full bg-beige" />
              ) : null}
            </button>
          )}
        </nav>

        <div className="p-4 mt-auto shrink-0">
          <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-4`}>
            <p className="text-sm font-normal text-foreground mb-1">
              {canManageBilling ? t.product.navPlans : t.product.navScale}
            </p>
            <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
              {canManageBilling ? t.product.navPlansBody : t.product.navScaleBody}
            </p>
            <Button
              asChild
              size="sm"
              className="w-full bg-beige text-cream hover:bg-beige-dark"
            >
              {canManageBilling ? (
                <Link to={BILLING_PATH}>{paywalled ? t.product.navChoosePlan : t.product.navManageBilling}</Link>
              ) : (
                <a href={DEMO_BOOKING_URL} target="_blank" rel="noopener noreferrer">
                  {t.product.navBookDemo}
                </a>
              )}
            </Button>
          </div>
        </div>
      </aside>

      <div className="lg:pl-60 flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden">
        <ImpersonationBanner />
        <header className="h-14 shrink-0 z-30 px-6 flex items-center justify-between bg-background border-b border-border">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>

          <div className="flex-1" />

          <div className="flex items-center gap-3">
            <div className="hidden md:block text-right">
              <p className="text-sm font-normal text-foreground leading-none">
                {user ? getUserDisplayName(user) : "User"}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {user?.companyName || "Vocify"}
              </p>
            </div>

            <span data-testid="session-sign-out">
              <IconAction
                label={t.product.navLogOut}
                tone="danger"
                onClick={() => {
                  void logout().then(() => window.location.replace("/login"));
                }}
              >
                <LogOut className="h-4 w-4" />
              </IconAction>
            </span>

            <Link
              to={impersonating ? "#" : "/dashboard/profile"}
              onClick={(e) => {
                if (impersonating) {
                  e.preventDefault();
                  returnToAdmin();
                }
              }}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card text-xs font-medium text-beige hover:border-beige/40 transition-colors"
            >
              {user ? getUserInitials(user) : "U"}
            </Link>
          </div>
        </header>

        <main className="flex-1 min-h-0 overflow-y-auto p-6 md:p-8">
          <Outlet />
        </main>
      </div>

      {askOpen ? (
        <aside
          className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-border bg-background"
          aria-label={t.product.askTitle}
        >
          <div className="flex items-center justify-between px-4 py-3">
            <p className={THEME_TOKENS.typography.sectionTitle}>{t.product.askTitle}</p>
            <Button variant="ghost" size="icon" aria-label={t.product.cancelAction} onClick={() => setAskOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
            <AskPanel embedded />
          </div>
        </aside>
      ) : null}

      {showDialer ? (
        <DialerChrome
          open={dialerOpen}
          onOpenChange={setDialerOpen}
          onCallStateChange={setCallState}
        />
      ) : null}
    </div>
    </DialerFocusProvider>
  );
};

function DialerChrome({
  open,
  onOpenChange,
  onCallStateChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCallStateChange: (state: CallState) => void;
}) {
  const { focus, clearFocus } = useDialerFocus();
  return (
    <FloatingDialer
      open={open}
      onOpenChange={onOpenChange}
      onCallStateChange={onCallStateChange}
      focusContact={focus}
      onFocusHandled={clearFocus}
    />
  );
}

export default DashboardLayout;
