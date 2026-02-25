import { Link } from "react-router-dom";
import { APP_URL } from "@/lib/app-url";
import { Button } from "@/components/ui/button";
import Logo from "@/components/Logo";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const Header = () => {
  const { language, setLanguage, t } = useLanguage();

  return (
    <motion.header 
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 bg-white/70 backdrop-blur-xl border-b border-border/40"
    >
      <div className="container mx-auto px-6 h-20 flex items-center justify-between">
            <div className="flex items-center gap-12">
              <Link 
                to={language === "ES" ? "/es" : "/"} 
                className="hover:opacity-80 transition-opacity"
              >
                <Logo />
              </Link>
              
              <nav className="hidden lg:flex items-center gap-10">
                <a href="#features" className="text-[10px] font-black tracking-[0.3em] uppercase text-muted-foreground/60 hover:text-beige transition-colors">
                  {t.nav.features}
                </a>
                <a href="#pricing" className="text-[10px] font-black tracking-[0.3em] uppercase text-muted-foreground/60 hover:text-beige transition-colors">
                  {t.nav.pricing}
                </a>
                <a href="#about" className="text-[10px] font-black tracking-[0.3em] uppercase text-muted-foreground/60 hover:text-beige transition-colors">
                  {t.nav.about}
                </a>
              </nav>
            </div>

        <div className="flex items-center gap-6">
          {/* Language Toggle */}
          <div className="hidden md:flex items-center bg-secondary/20 p-1 rounded-full border border-border/40">
            <button
              onClick={() => setLanguage("EN")}
              className={`px-3 py-1 rounded-full text-[10px] font-black transition-all ${
                language === "EN" ? "bg-white text-beige shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              EN
            </button>
            <button
              onClick={() => setLanguage("ES")}
              className={`px-3 py-1 rounded-full text-[10px] font-black transition-all ${
                language === "ES" ? "bg-white text-beige shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              ES
            </button>
          </div>

          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" asChild className="font-black tracking-[0.2em] uppercase text-[10px] text-muted-foreground hover:text-beige">
              <a href={`${APP_URL}/dashboard`}>{t.nav.login}</a>
            </Button>
            <Button size="sm" asChild className="bg-beige text-cream hover:bg-beige-dark shadow-soft font-black tracking-[0.2em] uppercase text-[10px] px-6 rounded-full transition-transform hover:scale-105 active:scale-95">
              <a href={`${APP_URL}/dashboard`}>{t.nav.getStarted}</a>
            </Button>
          </div>
        </div>
      </div>
    </motion.header>
  );
};

export default Header;
