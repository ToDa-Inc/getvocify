import { Link } from "react-router-dom";
import { ChevronsUpDown, CreditCard, LogOut, Monitor, Moon, Sun, User as UserIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSegmented,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/features/auth";
import { getUserDisplayName, getUserInitials } from "@/features/auth/types";
import { getImpersonation } from "@/lib/admin-impersonation";
import { useLanguage, type Language } from "@/lib/i18n";
import { useThemeMode } from "@/lib/theme-store";
import { parseThemeMode, type ThemeMode } from "@/lib/theme-mode";

const LANGUAGES: { lang: Language; labelKey: "languageSpanish" | "languageEnglish" }[] = [
  { lang: "ES", labelKey: "languageSpanish" },
  { lang: "EN", labelKey: "languageEnglish" },
];

const THEMES: { mode: ThemeMode; labelKey: "themeLight" | "themeDark" | "themeSystem"; Icon: typeof Sun }[] = [
  { mode: "light", labelKey: "themeLight", Icon: Sun },
  { mode: "dark", labelKey: "themeDark", Icon: Moon },
  { mode: "system", labelKey: "themeSystem", Icon: Monitor },
];

export type AvatarMenuBilling = { label: string; href: string; external?: boolean };

/**
 * Who is signed in, Perfil, Plan, Tema and Idioma (one segmented row each) and Cerrar sesión. `sidebar` is the account row at the
 * foot of the sidebar (desktop); the round avatar stays in the phone top bar. While an admin is
 * viewing as someone, Perfil is left out (the banner above carries "Return to admin").
 */
export function AvatarMenu({ variant = "avatar", billing = null }: { variant?: "avatar" | "sidebar"; billing?: AvatarMenuBilling | null }) {
  const { t, language, setLanguage } = useLanguage();
  const { user, logout } = useAuth();
  const { mode, setMode } = useThemeMode();
  const p = t.product;
  const impersonating = !!getImpersonation();

  return (
    <DropdownMenu>
      {variant === "sidebar" ? (
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={p.navAccountMenu}
            className="flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left transition-colors hover:bg-foreground/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-card text-[11px] font-medium text-beige">
              {user ? getUserInitials(user) : "U"}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] leading-tight text-foreground">{user ? getUserDisplayName(user) : "User"}</span>
              <span className="block truncate text-[11px] leading-tight text-muted-foreground">{user?.companyName || "Vocify"}</span>
            </span>
            <ChevronsUpDown aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
          </button>
        </DropdownMenuTrigger>
      ) : (
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={p.navAccountMenu}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card text-xs font-medium text-beige transition-colors hover:border-beige/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {user ? getUserInitials(user) : "U"}
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">{p.navAccountMenu}</TooltipContent>
      </Tooltip>
      )}
      <DropdownMenuContent
        align={variant === "sidebar" ? "start" : "end"}
        side={variant === "sidebar" ? "top" : "bottom"}
        className="w-60"
      >
        {user ? (
          <>
            <DropdownMenuLabel className="pb-2">
              <p className="truncate text-sm text-foreground">{getUserDisplayName(user)}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
          </>
        ) : null}
        {impersonating ? null : (
          <DropdownMenuItem asChild>
            <Link to="/dashboard/profile">
              <UserIcon aria-hidden />
              {p.navProfile}
            </Link>
          </DropdownMenuItem>
        )}
        {billing ? (
          <DropdownMenuItem asChild>
            {billing.external ? (
              <a href={billing.href} target="_blank" rel="noopener noreferrer">
                <CreditCard aria-hidden />
                {billing.label}
              </a>
            ) : (
              <Link to={billing.href}>
                <CreditCard aria-hidden />
                {billing.label}
              </Link>
            )}
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuSegmented
          label={p.navTheme}
          value={mode}
          onValueChange={(value) => setMode(parseThemeMode(value))}
          options={THEMES.map(({ mode: option, labelKey, Icon }) => ({
            value: option,
            label: p[labelKey],
            icon: <Icon aria-hidden strokeWidth={1.75} />,
          }))}
        />
        <DropdownMenuSegmented
          label={p.navLanguage}
          value={language}
          onValueChange={(value) => setLanguage(value as Language)}
          options={LANGUAGES.map(({ lang, labelKey }) => ({ value: lang, label: p[labelKey], short: lang }))}
        />
        <DropdownMenuSeparator />
        <DropdownMenuItem
          data-testid="session-sign-out"
          tone="danger"
          onSelect={() => {
            void logout().then(() => window.location.replace("/login"));
          }}
        >
          <LogOut aria-hidden />
          {p.navLogOut}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
