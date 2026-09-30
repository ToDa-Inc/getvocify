import { Link } from "react-router-dom";
import { LogOut, User as UserIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/features/auth";
import { getUserDisplayName, getUserInitials } from "@/features/auth/types";
import { getImpersonation } from "@/lib/admin-impersonation";
import { useLanguage, type Language } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { useThemeMode } from "@/lib/theme-store";
import { parseThemeMode, type ThemeMode } from "@/lib/theme-mode";

const LANGUAGES: { lang: Language; labelKey: "languageSpanish" | "languageEnglish" }[] = [
  { lang: "ES", labelKey: "languageSpanish" },
  { lang: "EN", labelKey: "languageEnglish" },
];

const THEMES: { mode: ThemeMode; labelKey: "themeLight" | "themeDark" | "themeSystem" }[] = [
  { mode: "light", labelKey: "themeLight" },
  { mode: "dark", labelKey: "themeDark" },
  { mode: "system", labelKey: "themeSystem" },
];

/**
 * The top bar's avatar: who is signed in, Perfil, Idioma, Tema and Cerrar sesión. While an admin is
 * viewing as someone, Perfil is left out (the banner above carries "Return to admin").
 */
export function AvatarMenu() {
  const { t, language, setLanguage } = useLanguage();
  const { user, logout } = useAuth();
  const { mode, setMode } = useThemeMode();
  const p = t.product;
  const impersonating = !!getImpersonation();

  return (
    <DropdownMenu>
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
      <DropdownMenuContent align="end" className="w-56">
        {user ? (
          <>
            <DropdownMenuLabel className="font-normal">
              <p className="truncate text-sm text-foreground">{getUserDisplayName(user)}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
          </>
        ) : null}
        {impersonating ? null : (
          <DropdownMenuItem asChild>
            <Link to="/dashboard/profile" className="gap-2">
              <UserIcon aria-hidden className="h-4 w-4 opacity-70" />
              {p.navProfile}
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuLabel className={THEME_TOKENS.typography.capsLabel}>{p.navLanguage}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={language} onValueChange={(value) => setLanguage(value as Language)}>
          {LANGUAGES.map(({ lang, labelKey }) => (
            <DropdownMenuRadioItem key={lang} value={lang}>
              {p[labelKey]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuLabel className={THEME_TOKENS.typography.capsLabel}>{p.navTheme}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={mode} onValueChange={(value) => setMode(parseThemeMode(value))}>
          {THEMES.map(({ mode: option, labelKey }) => (
            <DropdownMenuRadioItem key={option} value={option}>
              {p[labelKey]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          data-testid="session-sign-out"
          className="gap-2 text-destructive focus:text-destructive"
          onSelect={() => {
            void logout().then(() => window.location.replace("/login"));
          }}
        >
          <LogOut aria-hidden className="h-4 w-4" />
          {p.navLogOut}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
