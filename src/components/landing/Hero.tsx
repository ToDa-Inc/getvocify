import { ArrowRight, Play } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import WaveformCircle from "./WaveformCircle";
import RotatingText from "./RotatingText";

const Hero = () => {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-16 bg-mesh-gradient">
      <div className="container mx-auto px-6 py-20 text-center relative z-10">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="max-w-4xl mx-auto"
        >
          {/* Headline */}
          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tighter leading-[1.05] mb-6 text-balance">
            Stop Typing CRM Notes.
            <br />
            <span className="font-serif italic font-medium text-beige">Start Talking.</span>
          </h1>

          {/* Subheadline */}
          <motion.p 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
            className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed"
          >
            Voice memos that automatically update your CRM in 60 seconds.
            <br className="hidden md:block" />
            <span className="italic">Save 5+ hours per week.</span> Get back to selling.
          </motion.p>

          {/* CTA Buttons */}
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-12"
          >
            <Button variant="hero" size="xl" asChild className="group px-8">
              <Link to="/dashboard">
                Start Free Trial
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            <Button variant="outline" size="xl" asChild className="group px-8 bg-transparent hover:bg-white/10 backdrop-blur-sm border-beige/30">
              <Link to="#demo">
                <Play className="mr-2 h-4 w-4 fill-beige text-beige" />
                Watch 60-Second Demo
              </Link>
            </Button>
          </motion.div>

          {/* Trust Bar */}
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 0.8 }}
            className="flex flex-wrap items-center justify-center gap-4 md:gap-8 text-sm font-medium text-muted-foreground/80 mb-16"
          >
            <span className="flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-green-100 flex items-center justify-center text-[10px] text-green-700 font-bold">✓</span>
              Works with HubSpot, Salesforce & Pipedrive
            </span>
            <span className="hidden md:inline w-px h-4 bg-border/50" />
            <span className="flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-green-100 flex items-center justify-center text-[10px] text-green-700 font-bold">✓</span>
              GDPR Compliant · EU Data Storage
            </span>
            <span className="hidden md:inline w-px h-4 bg-border/50" />
            <span className="flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-green-100 flex items-center justify-center text-[10px] text-green-700 font-bold">✓</span>
              No credit card required
            </span>
          </motion.div>

          {/* Waveform Circle with Rotating Text */}
          <motion.div 
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, delay: 0.6, ease: "circOut" }}
            className="relative w-64 h-64 md:w-80 md:h-80 mx-auto"
          >
            <RotatingText />
            <WaveformCircle />
          </motion.div>
        </motion.div>
      </div>

      {/* Background elements */}
      <div className="absolute top-1/4 -left-20 w-96 h-96 bg-beige/5 rounded-full blur-[100px] -z-10 animate-pulse-wave" />
      <div className="absolute bottom-1/4 -right-20 w-96 h-96 bg-accent/5 rounded-full blur-[100px] -z-10 animate-pulse-wave" style={{ animationDelay: '1s' }} />
    </section>
  );
};

export default Hero;
