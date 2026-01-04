import { ArrowRight, Play, MousePointer2 } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import WaveformCircle from "./WaveformCircle";
import RotatingText from "./RotatingText";
import IntegrationsCarousel from "./IntegrationsCarousel";
import { useLanguage } from "@/lib/i18n";

const Hero = () => {
  const { t } = useLanguage();

  return (
    <section className="relative flex flex-col items-center justify-center overflow-hidden pt-32 pb-20 bg-mesh-gradient">
      <div className="container mx-auto px-6 text-center relative z-10 flex flex-col items-center justify-center">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="max-w-4xl mx-auto mb-20"
        >
          {/* Headline */}
          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tighter leading-[1.05] mb-6 text-balance">
            {t.hero.title1}
            <br />
            <span className="text-beige font-serif italic font-medium">{t.hero.title2}</span>
          </h1>

          {/* Subheadline */}
          <motion.p 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
            className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed"
          >
            {t.hero.subtitle1}
            <br className="hidden md:block" />
            <span className="font-serif italic font-medium">{t.hero.subtitle2}</span> {t.hero.subtitle3}
          </motion.p>

          {/* CTA Buttons */}
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
            className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-12"
          >
            <Button variant="hero" size="xl" asChild className="group px-8 rounded-full shadow-large hover:scale-105 transition-transform">
              <Link to="/dashboard">
                {t.hero.cta1}
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            <Button variant="outline" size="xl" asChild className="group px-8 bg-white/40 hover:bg-white/60 backdrop-blur-md border-beige/20 rounded-full transition-all">
              <Link to="#demo">
                <Play className="mr-2 h-4 w-4 fill-beige text-beige" />
                {t.hero.cta2}
              </Link>
            </Button>
          </motion.div>

          {/* Trust Bar */}
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 0.8 }}
            className="flex flex-wrap items-center justify-center gap-4 md:gap-8 text-[11px] font-bold uppercase tracking-widest text-muted-foreground/60 mb-16"
          >
            <span className="flex items-center gap-2">
              <span className="w-4 h-4 rounded-full bg-green-100 flex items-center justify-center text-[8px] text-green-700 font-black">✓</span>
              {t.hero.trust1}
            </span>
            <span className="hidden md:inline w-px h-3 bg-border/50" />
            <span className="flex items-center gap-2">
              <span className="w-4 h-4 rounded-full bg-green-100 flex items-center justify-center text-[8px] text-green-700 font-black">✓</span>
              {t.hero.trust2}
            </span>
            <span className="hidden md:inline w-px h-3 bg-border/50" />
            <span className="flex items-center gap-2">
              <span className="w-4 h-4 rounded-full bg-green-100 flex items-center justify-center text-[8px] text-green-700 font-black">✓</span>
              {t.hero.trust3}
            </span>
          </motion.div>

          {/* Waveform Circle with Rotating Text */}
          <motion.div 
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, delay: 0.6, ease: "circOut" }}
            className="relative w-64 h-64 md:w-80 md:h-80 mx-auto group cursor-pointer"
          >
            <RotatingText />
            <WaveformCircle />
          </motion.div>
        </motion.div>
      </div>

      <IntegrationsCarousel />

      {/* Background elements */}
      <div className="absolute top-1/4 -left-20 w-96 h-96 bg-beige/5 rounded-full blur-[100px] -z-10 animate-pulse-wave" />
      <div className="absolute bottom-1/4 -right-20 w-96 h-96 bg-accent/5 rounded-full blur-[100px] -z-10 animate-pulse-wave" style={{ animationDelay: '1s' }} />
    </section>
  );
};

export default Hero;
