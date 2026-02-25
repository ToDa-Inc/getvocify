import { ArrowRight, Play, Mail } from "lucide-react";
import { Link } from "react-router-dom";
import { APP_URL } from "@/lib/app-url";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";

const FinalCTA = () => {
  const { t } = useLanguage();
  
  return (
    <section className="py-32 bg-beige relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-4xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="mb-12"
          >
            <h2 className="text-4xl md:text-6xl font-bold text-cream mb-8 tracking-tighter leading-tight text-balance">
              {t.finalCta.title1} <br />
              <span className="text-white font-serif italic font-medium">{t.finalCta.title2}</span>
            </h2>
            <p className="text-cream/80 text-lg md:text-xl mb-12 max-w-2xl mx-auto leading-relaxed">
              {t.finalCta.subtitle}
            </p>
          </motion.div>

          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="bg-cream/5 backdrop-blur-md rounded-[3rem] p-10 md:p-16 mb-16 border border-cream/10 shadow-large"
          >
            <div className="grid md:grid-cols-2 gap-12 items-center">
              <div className="text-left">
                <p className="text-cream font-bold uppercase tracking-widest text-sm mb-8 opacity-60">{t.finalCta.onboarding}</p>
                <ol className="space-y-6">
                  {t.finalCta.steps.map((step: string, index: number) => (
                    <li key={index} className="flex items-start gap-4 text-cream">
                      <span className="flex-shrink-0 w-8 h-8 rounded-full bg-cream/10 flex items-center justify-center text-xs font-bold border border-cream/20">
                        {index + 1}
                      </span>
                      <span className="text-lg font-medium opacity-90 leading-tight">{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
              <div className="relative">
                <div className="aspect-square rounded-[2rem] bg-cream/10 border border-cream/20 flex flex-col items-center justify-center p-8 text-cream">
                  <div className="w-20 h-20 rounded-full bg-cream flex items-center justify-center mb-6 shadow-large">
                    <ArrowRight className="w-10 h-10 text-beige" />
                  </div>
                  <p className="text-2xl font-serif italic font-medium mb-2">{t.finalCta.trial}</p>
                  <p className="text-sm opacity-60">{t.finalCta.noCredit}</p>
                </div>
                {/* Decorative glow */}
                <div className="absolute inset-0 bg-cream/20 rounded-full blur-[100px] -z-10" />
              </div>
            </div>
          </motion.div>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 mb-16">
            <Button 
              size="xl" 
              asChild 
              className="group bg-cream text-beige hover:bg-white transition-all px-10 shadow-large rounded-full"
            >
              <a href={`${APP_URL}/dashboard`}>
                {t.finalCta.claim}
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </a>
            </Button>
            <Button 
              variant="outline" 
              size="xl" 
              asChild 
              className="group border-cream/30 text-cream hover:bg-cream/10 px-10 backdrop-blur-sm rounded-full"
            >
              <Link to="#demo">
                <Play className="mr-2 h-4 w-4 fill-cream" />
                {t.finalCta.watch}
              </Link>
            </Button>
          </div>

          <div className="flex flex-col items-center gap-4">
            <div className="flex items-center gap-2 text-cream/70 text-sm font-medium">
              <Mail className="w-4 h-4" />
              <span>{t.finalCta.questions} <span className="text-cream underline underline-offset-4">founders@vocify.com</span></span>
            </div>
            <p className="text-cream/40 text-[10px] uppercase tracking-widest font-bold">
              {t.finalCta.responseTime}
            </p>
          </div>
        </div>
      </div>
      
      {/* Background decoration */}
      <div className="absolute top-0 right-0 w-[600px] h-[600px] bg-white/5 rounded-full blur-[150px] -z-10" />
      <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-white/5 rounded-full blur-[150px] -z-10" />
    </section>
  );
};

export default FinalCTA;
