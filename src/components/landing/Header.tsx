import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import Logo from "@/components/Logo";
import { motion } from "framer-motion";

const Header = () => {
  return (
    <motion.header 
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 left-0 right-0 z-50 bg-white/70 backdrop-blur-xl border-b border-border/40"
    >
      <div className="container mx-auto px-6 h-20 flex items-center justify-between">
        <Link to="/" className="hover:opacity-80 transition-opacity">
          <Logo />
        </Link>
        
        <nav className="hidden md:flex items-center gap-10">
          <Link to="/#features" className="text-sm font-bold tracking-widest uppercase text-muted-foreground/60 hover:text-beige transition-colors">
            Features
          </Link>
          <Link to="/#pricing" className="text-sm font-bold tracking-widest uppercase text-muted-foreground/60 hover:text-beige transition-colors">
            Pricing
          </Link>
          <Link to="/#about" className="text-sm font-bold tracking-widest uppercase text-muted-foreground/60 hover:text-beige transition-colors">
            About
          </Link>
        </nav>

        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" asChild className="font-bold tracking-widest uppercase text-xs text-muted-foreground hover:text-beige">
            <Link to="/dashboard">Login</Link>
          </Button>
          <Button size="sm" asChild className="bg-beige text-cream hover:bg-beige-dark shadow-soft font-bold tracking-widest uppercase text-xs px-6">
            <Link to="/dashboard">Get Started</Link>
          </Button>
        </div>
      </div>
    </motion.header>
  );
};

export default Header;
