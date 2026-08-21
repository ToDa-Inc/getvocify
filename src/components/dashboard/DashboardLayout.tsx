import { useState } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { getUserDisplayName, getUserInitials } from "@/features/auth/types";
import {
  Home,
  Mic,
  Link2,
  BarChart3,
  Settings,
  Menu,
  X,
  Headphones,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import Logo from "@/components/Logo";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { DEMO_BOOKING_URL } from "@/lib/app-url";

const navItems = [
  { icon: Home, label: "Home", path: "/dashboard" },
  { icon: Mic, label: "Voice Memos", path: "/dashboard/memos" },
  { icon: Headphones, label: "Call Copilot", path: "/dashboard/copilot", beta: true },
  { icon: Link2, label: "Integrations", path: "/dashboard/integrations" },
  { icon: BarChart3, label: "Usage", path: "/dashboard/usage" },
  { icon: Settings, label: "Settings", path: "/dashboard/settings" },
];

const DashboardLayout = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const { user } = useAuth();

  const isActive = (path: string) => {
    if (path === "/dashboard") {
      return location.pathname === "/dashboard";
    }
    return location.pathname.startsWith(path);
  };

  return (
    <div className="dashboard-shell min-h-screen bg-background flex w-full">
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
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => setSidebarOpen(false)}
              className={`
                flex items-center gap-3 px-3 py-2 rounded-xl text-[13.5px] font-normal
                transition-colors duration-150
                ${isActive(item.path)
                  ? "bg-beige/10 text-foreground"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground"}
              `}
            >
              <item.icon className={`h-4 w-4 ${isActive(item.path) ? "text-beige" : "opacity-70"}`} />
              <span className="flex-1">{item.label}</span>
              {"beta" in item && item.beta && (
                <span className="text-[10px] font-medium text-beige">Beta</span>
              )}
            </Link>
          ))}
        </nav>

        <div className="p-4 mt-auto shrink-0">
          <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-4`}>
            <p className="text-sm font-normal text-foreground mb-1">Scale with us</p>
            <p className="text-xs text-muted-foreground mb-3 leading-relaxed">
              Unlimited memos and multi-CRM sync.
            </p>
            <Button
              asChild
              size="sm"
              className="w-full bg-beige text-cream hover:bg-beige-dark"
            >
              <a href={DEMO_BOOKING_URL} target="_blank" rel="noopener noreferrer">
                Book a demo
              </a>
            </Button>
          </div>
        </div>
      </aside>

      <div className="lg:pl-60 min-h-screen flex flex-col min-w-0 w-full">
        <header className="h-14 sticky top-0 z-30 px-6 flex items-center justify-between glass-panel border-b border-white/40 backdrop-blur-md">
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

            <Link
              to="/dashboard/profile"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card text-xs font-medium text-beige hover:border-beige/40 transition-colors"
            >
              {user ? getUserInitials(user) : "U"}
            </Link>
          </div>
        </header>

        <main className="flex-1 overflow-auto p-6 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
