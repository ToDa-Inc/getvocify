import { useCallback, useEffect, useMemo, useState } from "react";
import { Outlet, Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { getUserDisplayName } from "@/features/auth/types";
import {
  Home,
  Inbox,
  Settings,
  Menu,
  X,
  Phone,
  Users,
  GraduationCap,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import Logo from "@/components/Logo";
import { isAskShortcut } from "@/lib/ask-shortcut";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { ReportBell } from "@/components/dashboard/ReportBell";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import ImpersonationBanner from "@/components/admin/ImpersonationBanner";
import { AvatarMenu } from "@/components/dashboard/AvatarMenu";
import { FloatingDialer } from "@/components/dashboard/calling/FloatingDialer";
import { DialerFocusProvider, useDialerFocus } from "@/features/calling/DialerFocusProvider";
import { CALL_STATES, isInCall, type CallState } from "@/lib/dial-target";
import { companyCanUseDialer, companyIsPaywalled } from "@/lib/billing-access";
import AskPanel from "@/features/ask/components/AskPanel";
import { DesktopShellBridge } from "@/features/desktop/DesktopShellBridge";
import { isDesktopHost } from "@/lib/desktop-host";
import { isManagerRole, navItemsFor, topBarActions, type NavItemId } from "@/lib/nav";
import { HomeColumnContext } from "@/components/dashboard/HomeColumn";
import { useWideScreen } from "@/features/today/hooks/useWideScreen";

const NAV_ICONS: Record<NavItemId, LucideIcon> = {
  home: Home,
  interactions: Inbox,
  insights: Users,
  coach: GraduationCap,
  settings: Settings,
};

const BILLING_PATH = "/dashboard/settings/billing";

const DashboardLayout = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dialerOpen, setDialerOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [callState, setCallState] = useState<CallState>(CALL_STATES.IDLE);
  const [columnNode, setColumnNode] = useState<HTMLElement | null>(null);
  const location = useLocation();
  const { t } = useLanguage();
  const { user } = useAuth();
  const dialerLive = isInCall(callState);
  const dialerActive = dialerOpen || dialerLive;
  const canManageBilling = isManagerRole(user?.company?.role);
  const paywalled = companyIsPaywalled(user?.company);
  const repTopBar = topBarActions(user?.company?.role);
  const menu = navItemsFor({
    role: user?.company?.role,
    repWorkspace: user?.company?.repWorkspace,
  });

  // Ask is the floating sheet: /dashboard/ask (state.ask) and ⌘K / Ctrl+K open it.
  useEffect(() => {
    const state = location.state as { ask?: boolean } | null;
    if (state?.ask) setAskOpen(true);
  }, [location.state]);
  useEffect(() => {
    if (paywalled) return;
    const onKey = (event: KeyboardEvent) => {
      if (!isAskShortcut(event)) return;
      event.preventDefault();
      setAskOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paywalled]);
  const showDialer = !isDesktopHost() && !paywalled && companyCanUseDialer(user?.company);
  // The full Hoy (/dashboard/today) keeps its contact column whoever opens it, so its ContactPanel
  // always has somewhere to go on xl (its sheet is xl:hidden). Inicio (/dashboard) has its own rail.
  const homeColumn = location.pathname === "/dashboard/today";
  const closeAsk = useCallback(() => setAskOpen(false), []);
  const column = useMemo(
    () => ({ target: homeColumn ? columnNode : null, askOpen, closeAsk, canDial: showDialer }),
    [homeColumn, columnNode, askOpen, closeAsk, showDialer],
  );

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
    <HomeColumnContext.Provider value={column}>
    <DesktopShellBridge />
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
          {!paywalled && menu.items.map((item) => {
            const Icon = NAV_ICONS[item.id];
            const active = isActive(item.path);
            return (
              <Link
                key={item.id}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={`
                  flex items-center gap-3 px-3 py-2 text-[13.5px]
                  ${THEME_TOKENS.radius.pill} transition-colors duration-150
                  ${active
                    ? THEME_TOKENS.interaction.navPillActive
                    : THEME_TOKENS.interaction.navPillIdle}
                `}
              >
                <Icon className={`h-4 w-4 ${active ? "opacity-100" : "opacity-70"}`} />
                <span className="flex-1">{t.product[item.labelKey]}</span>
                {item.beta && (
                  <span className="text-[10px] font-medium text-beige">Beta</span>
                )}
              </Link>
            );
          })}
        </nav>

        {menu.showPlans && (
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
        )}
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

          {/* Llamar lives in the top bar for reps who can dial; the Head of Sales doesn't dial. */}
          <div className="flex flex-1 items-center gap-1.5 lg:gap-2">
            {repTopBar && showDialer ? (
              <button
                type="button"
                aria-label={t.product.navCall}
                aria-expanded={dialerOpen}
                onClick={() => setDialerOpen((current) => !current)}
                className={`inline-flex items-center gap-2 ${THEME_TOKENS.interaction.navPill} ${
                  dialerActive ? THEME_TOKENS.interaction.navPillActive : THEME_TOKENS.interaction.navPillIdle
                }`}
              >
                <Phone className={`h-4 w-4 ${dialerActive ? "opacity-100" : "opacity-70"}`} />
                <span className="hidden sm:inline">{t.product.navCall}</span>
                {dialerLive ? <span className="h-1.5 w-1.5 rounded-full bg-beige" /> : null}
              </button>
            ) : null}
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden md:block text-right">
              <p className="text-sm font-normal text-foreground leading-none">
                {user ? getUserDisplayName(user) : "User"}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {user?.companyName || "Vocify"}
              </p>
            </div>

            <AvatarMenu />
          </div>
        </header>

        {homeColumn ? (
          <div className="flex min-h-0 flex-1">
            <main className="min-w-0 flex-1 min-h-0 overflow-y-auto p-6 md:p-8">
              <Outlet />
            </main>
            <div
              ref={setColumnNode}
              className={
                askOpen
                  ? "hidden w-[400px] shrink-0 xl:block"
                  : "hidden w-[400px] shrink-0 overflow-y-auto border-l border-border/70 bg-card xl:block empty:hidden"
              }
            />
          </div>
        ) : (
          <main className="flex-1 min-h-0 overflow-y-auto p-6 md:p-8">
            <Outlet />
          </main>
        )}
      </div>

      {askOpen ? (
        <aside
          className={`ask-sheet ask-sheet-enter fixed inset-0 z-30 flex flex-col overflow-hidden sm:inset-y-3 sm:left-auto sm:right-3 sm:w-[min(440px,calc(100%-1.5rem))] sm:rounded-[20px] ${
            homeColumn ? "xl:top-[4.25rem] xl:w-[388px]" : ""
          }`}
          aria-label={t.product.askTitle}
        >
          <AskPanel onClose={() => setAskOpen(false)} />
        </aside>
      ) : null}

      {showDialer ? (
        <DialerChrome
          open={dialerOpen}
          onOpenChange={setDialerOpen}
          onCallStateChange={setCallState}
          homeColumn={homeColumn}
        />
      ) : null}
    </div>
    </HomeColumnContext.Provider>
    </DialerFocusProvider>
  );
};

function DialerChrome({
  open,
  onOpenChange,
  onCallStateChange,
  homeColumn,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCallStateChange: (state: CallState) => void;
  homeColumn: boolean;
}) {
  const { focus, clearFocus, reportLive, reportEnded } = useDialerFocus();
  const columnVisible = useWideScreen();
  return (
    <FloatingDialer
      open={open}
      onOpenChange={onOpenChange}
      onCallStateChange={onCallStateChange}
      focusContact={focus}
      onFocusHandled={clearFocus}
      placement={homeColumn && columnVisible ? "panel" : "floating"}
      onLiveReport={reportLive}
      onCallEnded={reportEnded}
    />
  );
}

export default DashboardLayout;
