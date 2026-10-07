import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Outlet, Link, Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { getUserDisplayName } from "@/features/auth/types";
import {
  Home,
  Settings,
  Menu,
  X,
  Phone,
  Users,
  GraduationCap,
  ListChecks,
  type LucideIcon,
  Workflow,
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
import { DialerDock } from "@/components/dashboard/calling/DialerDock";
import { DockHeader, DockPanel, DockTab, DockTabs } from "@/components/dashboard/RightDock";
import { TodayPanel } from "@/features/today/components/TodayPanel";
import { DialerFocusProvider, useDialerFocus } from "@/features/calling/DialerFocusProvider";
import { CALL_STATES, isInCall, type CallState } from "@/lib/dial-target";
import { companyCanUseDialer, companyIsPaywalled } from "@/lib/billing-access";
import AskPanel from "@/features/ask/components/AskPanel";
import { DesktopMeetingProvider } from "@/features/desktop/DesktopMeetingProvider";
import { DesktopCallProvider } from "@/features/desktop/DesktopCallProvider";
import { DesktopRecordingChip } from "@/features/desktop/DesktopRecordingChip";
import { DesktopSetupDialog } from "@/features/desktop/DesktopSetupDialog";
import { isDesktopHost } from "@/lib/desktop-host";
import { isManagerRole, isNavActive, navItemsFor, topBarActions, usesRepHome, type NavItemId } from "@/lib/nav";
import { HomeColumnContext } from "@/components/dashboard/HomeColumn";

const NAV_ICONS: Record<NavItemId, LucideIcon> = {
  home: Home,
  process: Workflow,
  insights: Users,
  coach: GraduationCap,
  settings: Settings,
};

const BILLING_PATH = "/dashboard/settings/billing";

const DashboardLayout = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // The right dock holds one panel at a time: the call panel (Llamar), later Hoy on Inicio.
  const [dock, setDock] = useState<"call" | "today" | null>(null);
  const [askOpen, setAskOpen] = useState(false);
  const [callState, setCallState] = useState<CallState>(CALL_STATES.IDLE);
  const [columnNode, setColumnNode] = useState<HTMLElement | null>(null);
  const location = useLocation();
  const { t } = useLanguage();
  const { user } = useAuth();
  const dialerLive = isInCall(callState);
  const dialerOpen = dock === "call";
  const setDialerOpen = useCallback(
    (open: boolean) => setDock((current) => (open ? "call" : current === "call" ? null : current)),
    [],
  );
  const canManageBilling = isManagerRole(user?.company?.role);
  const paywalled = companyIsPaywalled(user?.company);
  const repTopBar = topBarActions(user?.company?.role);
  // Hoy lives on the right of Inicio for a rep with the workspace: a panel you open and close.
  const todayDock = location.pathname === "/dashboard" && repTopBar && usesRepHome(user?.company);
  useEffect(() => {
    if (dock === "today" && !todayDock) setDock(null);
  }, [dock, todayDock]);
  const menu = navItemsFor({
    role: user?.company?.role,
    repWorkspace: user?.company?.repWorkspace,
  });
  const billing = !menu.showPlans
    ? null
    : canManageBilling
      ? { label: paywalled ? t.product.navChoosePlan : t.product.navManageBilling, href: BILLING_PATH }
      : { label: t.product.navBookDemo, href: DEMO_BOOKING_URL, external: true };

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
  // The desktop app calls from the notch island; its dashboard has no dialer of its own.
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

  return (
    <DesktopMeetingProvider>
    <DesktopCalling>
    <DialerFocusProvider onOpenDialer={() => setDialerOpen(true)}>
    <HomeColumnContext.Provider value={column}>
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
            {/* The wordmark is a dark raster: in dark it is inverted with its hues kept (gold mic, light text). */}
            <Logo size="sm" className="dark:[filter:invert(1)_hue-rotate(180deg)]" />
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
            const active = isNavActive(location.pathname, item);
            return (
              <Link
                key={item.id}
                to={item.path}
                aria-current={active ? "page" : undefined}
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

        {/* Desktop: the account (and plan) lives at the foot of the sidebar, so the page gets the top bar's height back. */}
        <div className="mt-auto hidden shrink-0 border-t border-border p-3 lg:block">
          {/* The top bar only shows below lg, so a live or unsent meeting stays reachable here at desktop widths. */}
          <div className="pb-2 empty:hidden">
            <DesktopRecordingChip />
          </div>
          <AvatarMenu variant="sidebar" billing={billing} />
        </div>
      </aside>

      <div
        className={`lg:pl-60 flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden transition-[margin] duration-200 ease-silk motion-reduce:transition-none ${
          dock && !homeColumn ? "xl:mr-[400px]" : ""
        }`}
      >
        <ImpersonationBanner />
        <header className="h-14 shrink-0 z-30 px-6 flex items-center justify-between bg-background border-b border-border lg:hidden">
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
            <DesktopRecordingChip />
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

            <AvatarMenu billing={billing} />
          </div>
        </header>

        {homeColumn ? (
          <div className="flex min-h-0 flex-1">
            <main className="app-scroll min-w-0 flex-1 min-h-0 overflow-y-auto p-6 md:p-8">
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
          <main className="app-scroll flex-1 min-h-0 overflow-y-auto p-6 md:p-8">
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

      {dock ? (
        <div className="fixed inset-0 z-30 bg-foreground/20 xl:hidden" onClick={() => setDock(null)} aria-hidden />
      ) : null}

      {dock === "today" && todayDock ? (
        <DockPanel open label={t.product.todayTitle}>
          <DockHeader title={t.product.todayTitle} closeLabel={t.product.askClose} onClose={() => setDock(null)} />
          <TodayPanel />
        </DockPanel>
      ) : null}

      {showDialer ? (
        <DialerDockMount open={dialerOpen} onOpenChange={setDialerOpen} onCallStateChange={setCallState} />
      ) : null}

      {dock === null && !askOpen ? (
        <DockTabs>
          {todayDock ? <DockTab label={t.product.todayTitle} icon={ListChecks} onClick={() => setDock("today")} /> : null}
          {repTopBar && showDialer ? (
            <CallTab live={dialerLive} onOpen={() => setDialerOpen(true)} label={t.product.navCall} />
          ) : null}
        </DockTabs>
      ) : null}
      <DesktopSetupDialog />
    </div>
    </HomeColumnContext.Provider>
    </DialerFocusProvider>
    </DesktopCalling>
    </DesktopMeetingProvider>
  );
};

/** Calling the contact on screen from the island: only inside the desktop app. */
function DesktopCalling({ children }: { children: ReactNode }) {
  return isDesktopHost() ? <DesktopCallProvider>{children}</DesktopCallProvider> : <>{children}</>;
}

/** The call dock lives inside the focus provider so a contact's own "Llamar" can open it. */
function DialerDockMount({
  open,
  onOpenChange,
  onCallStateChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCallStateChange: (state: CallState) => void;
}) {
  const { focus, clearFocus, reportLive, reportEnded } = useDialerFocus();
  return (
    <DialerDock
      open={open}
      onOpenChange={onOpenChange}
      onCallStateChange={onCallStateChange}
      focusContact={focus}
      onFocusHandled={clearFocus}
      onLiveReport={reportLive}
      onCallEnded={reportEnded}
    />
  );
}

/** The slim "Llamar" tab on the right edge: lit, with the running time, while a call is in progress. */
function CallTab({ live, onOpen, label }: { live: boolean; onOpen: () => void; label: string }) {
  const { liveElapsed } = useDialerFocus();
  return <DockTab label={label} icon={Phone} onClick={onOpen} live={live} liveText={liveElapsed} />;
}

export default DashboardLayout;
