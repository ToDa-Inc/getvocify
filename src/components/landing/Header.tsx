import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart3, Briefcase, Building, CalendarClock, CheckCheck, ChevronDown, Database, Headphones, Car, Menu, Phone, type LucideIcon } from "lucide-react";
import { APP_URL, DEMO_BOOKING_URL } from "@/lib/app-url";
import Logo from "@/components/Logo";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import { ROLE_PATHS } from "@/lib/landing-roles";
import { Sheet, SheetContent, SheetTrigger, SheetClose } from "@/components/ui/sheet";

const HEADER_ZONE = 80;

const Header = () => {
  const { language, setLanguage, t } = useLanguage();
  const [isOverDark, setIsOverDark] = useState(false);

  const home = language === "EN" ? "/en" : "/";
  const [openMenu, setOpenMenu] = useState<"product" | "teams" | null>(null);

  const menus: { id: "product" | "teams"; label: string; items: { icon: LucideIcon; href: string; title: string; desc: string }[] }[] = [
    {
      id: "product",
      label: t.nav.product,
      items: [
        { icon: CalendarClock, href: `${home}#demo-before` },
        { icon: Headphones, href: `${home}#demo-during` },
        { icon: CheckCheck, href: `${home}#demo-after` },
        { icon: BarChart3, href: `${home}#coaching` },
      ].map((item, i) => ({ ...item, ...t.nav.menus.product[i] })),
    },
    {
      id: "teams",
      label: t.nav.teams,
      items: [
        { icon: Phone, href: ROLE_PATHS.sdr },
        { icon: Building, href: ROLE_PATHS.ae },
        { icon: Briefcase, href: ROLE_PATHS.manager },
        { icon: Car, href: ROLE_PATHS.field },
        { icon: Database, href: ROLE_PATHS.revops },
      ].map((item, i) => ({ ...item, ...t.nav.menus.teams[i] })),
    },
  ];

  useEffect(() => {
    let raf = 0;
    const check = () => {
      const overDark = Array.from(document.querySelectorAll(".bg-ink")).some((el) => {
        const rect = el.getBoundingClientRect();
        return rect.top <= HEADER_ZONE && rect.bottom >= 0;
      });
      setIsOverDark(overDark);
    };
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(check);
    };
    check();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-4 left-0 right-0 z-50 px-4"
    >
      <div
        className={`mx-auto flex h-14 max-w-4xl items-center justify-between rounded-full pl-5 pr-2 transition-colors duration-300 ${
          isOverDark ? "glass-card-dark" : "glass-card-strong"
        }`}
      >
        <Link
          to={language === "EN" ? "/en" : "/"}
          className="shrink-0 transition-opacity hover:opacity-80"
        >
          <Logo onDark={isOverDark} />
        </Link>

        <nav className="hidden lg:flex flex-1 items-center justify-center gap-1" onMouseLeave={() => setOpenMenu(null)}>
          {menus.map((menu) => (
            <div key={menu.id} className="relative" onMouseEnter={() => setOpenMenu(menu.id)}>
              <button
                type="button"
                aria-expanded={openMenu === menu.id}
                onClick={() => setOpenMenu(openMenu === menu.id ? null : menu.id)}
                onKeyDown={(e) => e.key === "Escape" && setOpenMenu(null)}
                className={`flex items-center gap-1 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                  isOverDark
                    ? "text-cream/60 hover:text-cream hover:bg-white/5"
                    : "text-foreground/60 hover:text-foreground hover:bg-beige/5"
                } ${openMenu === menu.id ? (isOverDark ? "text-cream" : "text-foreground") : ""}`}
              >
                {menu.label}
                <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-300 ${openMenu === menu.id ? "rotate-180" : ""}`} />
              </button>
              {openMenu === menu.id && (
                <div className="absolute left-1/2 top-full z-50 w-[540px] -translate-x-1/2 pt-4">
                  <motion.div
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18 }}
                    className="glass-card-strong grid grid-cols-2 gap-1 rounded-3xl !bg-white p-3 shadow-float"
                  >
                    {menu.items.map((item) => (
                      <Link
                        key={item.title}
                        to={item.href}
                        onClick={() => setOpenMenu(null)}
                        className="group flex gap-3 rounded-2xl p-3 transition-colors hover:bg-beige/10"
                      >
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-tone-sand text-beige">
                          <item.icon className="h-4 w-4" strokeWidth={1.7} />
                        </span>
                        <span>
                          <span className="block text-sm font-semibold text-foreground">{item.title}</span>
                          <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">{item.desc}</span>
                        </span>
                      </Link>
                    ))}
                  </motion.div>
                </div>
              )}
            </div>
          ))}
          <Link
            to="/mcp"
            className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              isOverDark
                ? "text-cream/60 hover:text-cream hover:bg-white/5"
                : "text-foreground/60 hover:text-foreground hover:bg-beige/5"
            }`}
          >
            {t.nav.mcp}
          </Link>
        </nav>

        <div className="flex items-center gap-2">
          {/* Language Toggle */}
          <div
            className={`hidden md:flex items-center rounded-full p-1 ring-1 transition-colors ${
              isOverDark ? "bg-white/5 ring-white/10" : "bg-beige/5 ring-border/60"
            }`}
          >
            {(["EN", "ES"] as const).map((lang) => (
              <button
                key={lang}
                onClick={() => setLanguage(lang)}
                className={`rounded-full px-3 py-1 font-mono text-[10px] font-medium uppercase tracking-widest transition-all ${
                  language === lang
                    ? isOverDark
                      ? "bg-white/15 text-cream shadow-soft"
                      : "bg-white text-beige shadow-soft"
                    : isOverDark
                      ? "text-cream/50 hover:text-cream"
                      : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {lang}
              </button>
            ))}
          </div>

          <a
            href={`${APP_URL}/dashboard`}
            className={`hidden sm:block rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              isOverDark ? "text-cream/60 hover:text-cream" : "text-foreground/60 hover:text-foreground"
            }`}
          >
            {t.nav.login}
          </a>
          <a
            href={DEMO_BOOKING_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-glow inline-flex items-center rounded-full bg-beige px-5 py-2.5 text-sm font-semibold text-cream transition-snap hover:bg-beige-dark active:scale-[0.98]"
          >
            {t.nav.getStarted}
          </a>

          {/* Mobile menu */}
          <Sheet>
            <SheetTrigger asChild>
              <button
                type="button"
                aria-label="Open menu"
                className={`flex lg:hidden size-9 items-center justify-center rounded-full transition-colors ${
                  isOverDark ? "text-cream hover:bg-white/10" : "text-foreground hover:bg-beige/10"
                }`}
              >
                <Menu className="h-5 w-5" />
              </button>
            </SheetTrigger>
            <SheetContent side="right" className="bg-cream border-l border-border/50 w-72">
              <nav className="mt-10 flex flex-col gap-1 overflow-y-auto">
                {menus.map((menu) => (
                  <div key={menu.id} className="mb-3">
                    <p className="px-4 pb-1 text-xs font-medium text-muted-foreground">
                      {menu.label}
                    </p>
                    {menu.items.map((item) => (
                      <SheetClose key={item.title} asChild>
                        <Link
                          to={item.href}
                          className="block rounded-2xl px-4 py-2.5 text-base font-medium text-foreground/80 transition-colors hover:bg-beige/10 hover:text-foreground"
                        >
                          {item.title}
                        </Link>
                      </SheetClose>
                    ))}
                  </div>
                ))}
                <SheetClose asChild>
                  <Link
                    to="/mcp"
                    className="rounded-2xl px-4 py-3 text-base font-medium text-foreground/80 transition-colors hover:bg-beige/10 hover:text-foreground"
                  >
                    {t.nav.mcp}
                  </Link>
                </SheetClose>
                <SheetClose asChild>
                  <Link
                    to="/download"
                    className="rounded-2xl px-4 py-3 text-base font-medium text-foreground/80 transition-colors hover:bg-beige/10 hover:text-foreground"
                  >
                    {t.nav.download}
                  </Link>
                </SheetClose>
                <SheetClose asChild>
                  <a
                    href={`${APP_URL}/dashboard`}
                    className="rounded-2xl px-4 py-3 text-base font-medium text-foreground/80 transition-colors hover:bg-beige/10 hover:text-foreground"
                  >
                    {t.nav.login}
                  </a>
                </SheetClose>
              </nav>

              <div className="mt-6 flex items-center gap-2 px-4">
                {(["EN", "ES"] as const).map((lang) => (
                  <button
                    key={lang}
                    onClick={() => setLanguage(lang)}
                    className={`rounded-full px-4 py-2 font-mono text-xs font-medium uppercase tracking-widest transition-all ${
                      language === lang
                        ? "bg-beige text-cream"
                        : "bg-beige/5 text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {lang}
                  </button>
                ))}
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </motion.header>
  );
};

export default Header;
