import { motion, useAnimationControls } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import { useEffect } from "react";

const integrations = [
  { name: "HubSpot", logo: "https://cdn.worldvectorlogo.com/logos/hubspot.svg" },
  { name: "Salesforce", logo: "https://cdn.worldvectorlogo.com/logos/salesforce-2.svg" },
  { name: "Pipedrive", logo: "https://cdn.worldvectorlogo.com/logos/pipedrive.svg" },
  { name: "Slack", logo: "https://cdn.worldvectorlogo.com/logos/slack-new-logo.svg" },
  { name: "Zoho", logo: "https://cdn.worldvectorlogo.com/logos/zoho-1.svg" },
];

const IntegrationsCarousel = () => {
  const { t } = useLanguage();

  return (
    <div className="w-full py-20 overflow-hidden bg-white/5 border-y border-border/50">
      <div className="container mx-auto px-6 mb-16">
        <p className="text-center text-sm md:text-lg font-bold uppercase tracking-[0.4em] text-muted-foreground/60">
          {t.integrations.text1} <span className="font-serif italic font-medium text-beige opacity-80 text-lg md:text-2xl ml-1 mr-1">{t.integrations.text2}</span> {t.integrations.text3}
        </p>
      </div>
      
      <div className="relative flex overflow-hidden group">
        <motion.div 
          animate={{ x: ["0%", "-50%"] }}
          transition={{ 
            duration: 30, 
            repeat: Infinity, 
            ease: "linear",
          }}
          className="flex whitespace-nowrap gap-32 items-center"
        >
          {/* We duplicate the array to ensure seamless looping */}
          {[...integrations, ...integrations, ...integrations, ...integrations].map((item, index) => (
            <div 
              key={`${item.name}-${index}`} 
              className="grayscale opacity-30 hover:grayscale-0 hover:opacity-100 transition-all duration-700 cursor-pointer flex-shrink-0"
            >
              <img 
                src={item.logo} 
                alt={item.name} 
                className="h-12 w-auto object-contain max-w-[160px]"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = `https://ui-avatars.com/api/?name=${item.name}&background=f5f5f5&color=999`;
                }}
              />
            </div>
          ))}
        </motion.div>
      </div>
    </div>
  );
};

export default IntegrationsCarousel;
