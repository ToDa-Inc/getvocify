import { Link } from "react-router-dom";
import Logo from "@/components/Logo";

const Footer = () => {
  return (
    <footer className="py-12 bg-background border-t border-border">
      <div className="container mx-auto px-6">
        <div className="flex flex-col md:flex-row items-center justify-between gap-6">
          <Logo size="sm" />
          
          <nav className="flex items-center gap-8">
            <Link to="/#features" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              Product
            </Link>
            <Link to="/#pricing" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              Pricing
            </Link>
            <Link to="/#about" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              About
            </Link>
            <Link to="/help" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              Help
            </Link>
          </nav>
          
          <p className="text-sm text-muted-foreground">
            © 2025 Vocify
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
