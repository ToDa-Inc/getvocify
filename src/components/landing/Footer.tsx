import { Link } from "react-router-dom";
import { DEMO_BOOKING_URL } from "@/lib/app-url";
import Logo from "@/components/Logo";
import { useLanguage } from "@/lib/i18n";
import { ROLE_PATHS } from "@/lib/landing-roles";

const Footer = () => {
  const { language, t } = useLanguage();
  const f = t.footer;
  const home = language === "EN" ? "/en" : "/";

  return (
    <footer className="py-24 bg-background border-t border-border/50">
      <div className="container mx-auto px-6">
        <div className="grid md:grid-cols-5 gap-12 mb-16">
          <div className="col-span-1 md:col-span-2">
            <Link to={home} className="inline-block mb-8">
              <Logo size="md" />
            </Link>
            <p className="text-muted-foreground max-w-sm leading-relaxed">{f.tagline}</p>
          </div>

          <div>
            <h4 className="text-sm font-medium text-foreground mb-8">{f.product}</h4>
            <nav className="flex flex-col gap-4">
              <Link
                to={`${home}#how-it-works`}
                className="text-sm text-muted-foreground hover:text-beige transition-colors"
              >
                {f.links.how}
              </Link>
              <Link to={`${home}#coaching`} className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {f.links.coaching}
              </Link>
              <Link to="/mcp" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {f.links.mcp}
              </Link>
              <Link to="/docs" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {f.links.docs}
              </Link>
              <Link to="/support" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {f.links.support}
              </Link>
              <a
                href={DEMO_BOOKING_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-muted-foreground hover:text-beige transition-colors"
              >
                {f.links.demo}
              </a>
            </nav>
          </div>

          <div>
            <h4 className="mb-8 text-sm font-medium text-foreground">{f.teams}</h4>
            <nav className="flex flex-col gap-4">
              {(["sdr", "ae", "manager", "field", "revops"] as const).map((role) => (
                <Link key={role} to={ROLE_PATHS[role]} className="text-sm text-muted-foreground transition-colors hover:text-beige">
                  {t.nav.menus.teams[["sdr", "ae", "manager", "field", "revops"].indexOf(role)].title}
                </Link>
              ))}
            </nav>
          </div>

          <div>
            <h4 className="text-sm font-medium text-foreground mb-8">{f.company}</h4>
            <nav className="flex flex-col gap-4">
              <Link to="/about" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {f.links.about}
              </Link>
              <Link to="/blog" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {f.links.blog}
              </Link>
              <Link to="/privacy" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {f.links.privacy}
              </Link>
              <Link to="/terms" className="text-sm text-muted-foreground hover:text-beige transition-colors">
                {f.links.terms}
              </Link>
            </nav>
          </div>
        </div>

        <div className="pt-12 border-t border-border/50 flex flex-col md:flex-row items-center justify-between gap-6">
          <p className="text-xs text-muted-foreground/70">
            © {new Date().getFullYear()} Vocify. {f.rights}
          </p>
          <p className="text-xs text-muted-foreground/70">
            <span className="text-beige mx-1">♥</span> {f.madeFor}
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
