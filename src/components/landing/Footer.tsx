import { Link } from "react-router-dom";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import Logo from "@/components/Logo";
import { useLanguage } from "@/lib/i18n";

const Footer = () => {
  const { language, t } = useLanguage();
  const home = language === "EN" ? "/en" : "/";

  return (
    <footer className="py-24 bg-background border-t border-border/50">
      <div className="container mx-auto px-6">
        <div className="grid md:grid-cols-4 gap-12 mb-16">
          <div className="col-span-1 md:col-span-2">
            <Link to={home} className="inline-block mb-8">
              <Logo size="md" />
            </Link>
            <p className="text-muted-foreground max-w-sm leading-relaxed">
              The copilot that updates your CRM while you keep selling. No admin, no data left behind.
            </p>
          </div>

          <div>
            <h4 className="font-mono text-[11px] font-medium uppercase tracking-[0.25em] text-foreground mb-8">Product</h4>
            <nav className="flex flex-col gap-4">
              <Link to={`${home}#features`} className="text-sm text-muted-foreground hover:text-beige transition-colors">
                Features
              </Link>
              <Link to={`${home}#calculator`} className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {t.nav.calculator}
              </Link>
              <Link
                to={`${home}#how-it-works`}
                className="text-sm text-muted-foreground hover:text-beige transition-colors"
              >
                How it works
              </Link>
              <a
                href={DEMO_BOOKING_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-muted-foreground hover:text-beige transition-colors"
              >
                Book a Demo
              </a>
            </nav>
          </div>

          <div>
            <h4 className="font-mono text-[11px] font-medium uppercase tracking-[0.25em] text-foreground mb-8">Company</h4>
            <nav className="flex flex-col gap-4">
              <Link to="/about" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                About Us
              </Link>
              <Link to="/blog" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                Blog
              </Link>
              <Link to="/privacy" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                Privacy Policy
              </Link>
              <Link to="/terms" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                Terms of Service
              </Link>
            </nav>
          </div>
        </div>

        <div className="pt-12 border-t border-border/50 flex flex-col md:flex-row items-center justify-between gap-6">
          <p className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/60">
            © {new Date().getFullYear()} Vocify. All rights reserved.
          </p>
          <p className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/60">
            Made with <span className="text-beige mx-1">♥</span> for sales teams.
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
