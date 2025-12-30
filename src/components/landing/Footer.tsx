import { Link } from "react-router-dom";
import Logo from "@/components/Logo";
import { Mail, Linkedin, Twitter, Github } from "lucide-react";

const Footer = () => {
  return (
    <footer className="py-24 bg-background border-t border-border/50">
      <div className="container mx-auto px-6">
        <div className="grid md:grid-cols-4 gap-12 mb-16">
          <div className="col-span-1 md:col-span-2">
            <Link to="/" className="inline-block mb-8">
              <Logo size="md" />
            </Link>
            <p className="text-muted-foreground max-w-sm mb-8 leading-relaxed">
              The voice-first CRM update tool for elite sales teams. Reclaim your selling time and keep your data clean effortlessly.
            </p>
            <div className="flex items-center gap-4">
              <a href="#" className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:bg-beige hover:text-cream transition-all">
                <Linkedin className="w-4 h-4" />
              </a>
              <a href="#" className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:bg-beige hover:text-cream transition-all">
                <Twitter className="w-4 h-4" />
              </a>
              <a href="#" className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:bg-beige hover:text-cream transition-all">
                <Mail className="w-4 h-4" />
              </a>
            </div>
          </div>
          
          <div>
            <h4 className="text-xs font-bold uppercase tracking-[0.2em] text-foreground mb-8">Product</h4>
            <nav className="flex flex-col gap-4">
              <Link to="/#features" className="text-sm text-muted-foreground hover:text-beige transition-colors">Features</Link>
              <Link to="/#pricing" className="text-sm text-muted-foreground hover:text-beige transition-colors">Pricing</Link>
              <Link to="/#about" className="text-sm text-muted-foreground hover:text-beige transition-colors">How it works</Link>
              <Link to="/dashboard" className="text-sm text-muted-foreground hover:text-beige transition-colors">Start Free Trial</Link>
            </nav>
          </div>

          <div>
            <h4 className="text-xs font-bold uppercase tracking-[0.2em] text-foreground mb-8">Company</h4>
            <nav className="flex flex-col gap-4">
              <Link to="/about" className="text-sm text-muted-foreground hover:text-beige transition-colors">About Us</Link>
              <Link to="/blog" className="text-sm text-muted-foreground hover:text-beige transition-colors">Blog</Link>
              <Link to="/privacy" className="text-sm text-muted-foreground hover:text-beige transition-colors">Privacy Policy</Link>
              <Link to="/terms" className="text-sm text-muted-foreground hover:text-beige transition-colors">Terms of Service</Link>
            </nav>
          </div>
        </div>
        
        <div className="pt-12 border-t border-border/50 flex flex-col md:flex-row items-center justify-between gap-6">
          <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/60">
            © 2025 Vocify. All rights reserved.
          </p>
          <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/60">
            Made with <span className="text-beige mx-1">♥</span> for sales teams.
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
