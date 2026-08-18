import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Menu } from "lucide-react";
import { APP_URL, DEMO_BOOKING_URL } from "@/lib/app-url";
import Logo from "@/components/Logo";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import { Sheet, SheetContent, SheetTrigger, SheetClose } from "@/components/ui/sheet";

const HEADER_ZONE = 80;

const Header = () => {
  const { language, setLanguage, t } = useLanguage();
  const [isOverDark, setIsOverDark] = useState(false);

  const navLinks = [
    { href: "#features", label: t.nav.features },
    { href: "#calculator", label: t.nav.calculator },
    { href: "#how-it-works", label: t.nav.about },
  ];

  useEffect(() => {
    let raf = 0;
    const check = () => {
      const darkSection = document.querySelector(".bg-ink");
      if (!darkSection) {
        setIsOverDark(false);
        return;
      }
      const rect = darkSection.getBoundingClientRect();
      setIsOverDark(rect.top <= HEADER_ZONE && rect.bottom >= 0);
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
          <Logo className={`transition-all duration-300 ${isOverDark ? "brightness-0 invert" : ""}`} />
        </Link>

        <nav className="hidden lg:flex flex-1 items-center justify-center gap-1">
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                isOverDark
                  ? "text-cream/60 hover:text-cream hover:bg-white/5"
                  : "text-foreground/60 hover:text-foreground hover:bg-beige/5"
              }`}
            >
              {link.label}
            </a>
          ))}
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
              <nav className="mt-10 flex flex-col gap-1">
                {navLinks.map((link) => (
                  <SheetClose key={link.href} asChild>
                    <a
                      href={link.href}
                      className="rounded-2xl px-4 py-3 text-base font-medium text-foreground/80 transition-colors hover:bg-beige/10 hover:text-foreground"
                    >
                      {link.label}
                    </a>
                  </SheetClose>
                ))}
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
