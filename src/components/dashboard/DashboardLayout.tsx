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
  Sparkles,
  User,
  LogOut
} from "lucide-react";
import { Button } from "@/components/ui/button";
import Logo from "@/components/Logo";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const navItems = [
  { icon: Home, label: "Home", path: "/dashboard" },
  { icon: Mic, label: "Voice Memos", path: "/dashboard/memos" },
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
    <div className="min-h-screen bg-background flex w-full">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-foreground/20 z-40 lg:hidden backdrop-blur-sm"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside 
        className={`
          fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white border-r border-border/40
          transform transition-transform duration-300 lg:transform-none
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-8 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Logo size="sm" />
              <span className="px-2 py-0.5 text-[8px] font-black uppercase tracking-widest bg-beige/10 text-beige rounded-full border border-beige/20">
                PRO
              </span>
            </div>
            <Button 
              variant="ghost" 
              size="icon" 
              className="lg:hidden rounded-full"
              onClick={() => setSidebarOpen(false)}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 space-y-2 mt-4">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={`
                  flex items-center gap-4 px-6 py-3.5 rounded-full text-sm font-bold tracking-tight
                  transition-all duration-300
                  ${isActive(item.path) 
                    ? 'bg-beige text-cream shadow-medium scale-[1.02]' 
                    : 'text-muted-foreground hover:bg-beige/5 hover:text-beige'
                  }
                `}
              >
                <item.icon className={`h-5 w-5 ${isActive(item.path) ? 'text-cream' : 'opacity-40'}`} />
                {item.label}
              </Link>
            ))}
          </nav>

          {/* Upgrade Card */}
          <div className="p-6">
            <div className={`${THEME_TOKENS.cards.premium} p-6 border border-white/20 relative overflow-hidden group rounded-[2rem]`}>
              <div className="absolute inset-0 bg-gradient-to-br from-beige/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <div className="relative z-10">
                <div className="flex items-center gap-2 mb-3">
                  <Sparkles className="h-4 w-4 text-beige" />
                  <span className={THEME_TOKENS.typography.capsLabel + " !text-foreground"}>Go Pro</span>
                </div>
                <p className="text-[11px] text-muted-foreground mb-4 leading-relaxed font-medium">
                  Unlock unlimited memos and sync with any CRM.
                </p>
                <Button size="sm" className="w-full bg-beige text-cream hover:bg-beige-dark rounded-full text-[10px] font-black uppercase tracking-widest shadow-soft transition-transform hover:scale-[1.02] active:scale-95">
                  Upgrade
                </Button>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header */}
        <header className="h-20 border-b border-border/40 bg-white/50 backdrop-blur-xl flex items-center justify-between px-8 sticky top-0 z-30">
          <Button 
            variant="ghost" 
            size="icon" 
            className="lg:hidden rounded-full"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </Button>

          <div className="flex-1" />

          {/* User Menu */}
          <div className="flex items-center gap-4">
            <div className="hidden md:block text-right mr-2">
              <p className="text-xs font-bold text-foreground leading-none">
                {user ? getUserDisplayName(user) : 'User'}
              </p>
              <p className="text-[10px] font-medium text-muted-foreground mt-1">
                {user?.companyName || 'Free Plan'}
              </p>
            </div>
            
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="relative h-10 w-10 rounded-full p-0 border border-border/40 shadow-soft overflow-hidden group">
                  <div className="absolute inset-0 bg-beige/10 opacity-0 group-hover:opacity-100 transition-opacity" />
                  <span className="text-xs font-black text-beige">
                    {user ? getUserInitials(user) : 'U'}
                  </span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 mt-2 rounded-2xl border-border/40 shadow-large p-2">
                <DropdownMenuItem asChild className="rounded-xl cursor-pointer py-3">
                  <Link to="/dashboard/settings" className="flex items-center gap-3">
                    <User className="h-4 w-4 text-muted-foreground" />
                    <span className="font-bold text-sm">My Profile</span>
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem asChild className="rounded-xl cursor-pointer py-3">
                  <Link to="/dashboard/settings" className="flex items-center gap-3">
                    <Settings className="h-4 w-4 text-muted-foreground" />
                    <span className="font-bold text-sm">Settings</span>
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator className="my-2 bg-border/40" />
                <DropdownMenuItem asChild className="rounded-xl cursor-pointer py-3 text-destructive hover:bg-destructive/5">
                  <Link to="/" className="flex items-center gap-3">
                    <LogOut className="h-4 w-4" />
                    <span className="font-bold text-sm">Logout</span>
                  </Link>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto p-8 bg-secondary/5">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
