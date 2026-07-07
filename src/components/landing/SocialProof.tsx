import { motion } from "framer-motion";
import { Quote } from "lucide-react";

import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";
import ScrollScrubItem from "./ScrollScrubItem";

const fanRotations = [-4, 4, -3, 3];

const SocialProof = () => {
  const { t } = useLanguage();

  const testimonials = [
    { quote: t.socialProof.q1 },
    { quote: t.socialProof.q2 },
    { quote: t.socialProof.q3 },
    { quote: t.socialProof.q4 },
  ];

  return (
    <section className="py-32 bg-secondary/30 relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <motion.div {...blurReveal()} className="text-center mb-16">
          <span className="section-label mb-6">04 — {t.socialProof.label}</span>
          <h2 className="text-3xl md:text-5xl font-semibold text-foreground mb-6 tracking-tighter">
            {t.socialProof.title1} <span className="text-beige font-serif italic font-medium">{t.socialProof.title2}</span>
          </h2>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto">
          {testimonials.map((testimonial, index) => (
            <ScrollScrubItem
              key={index}
              rotate={fanRotations[index % fanRotations.length]}
              className="glass-card rounded-[28px] p-8 flex flex-col hover:shadow-float transition-shadow duration-500 ease-silk will-change-transform"
            >
              <div className="mb-6">
                <Quote className="w-10 h-10 text-beige/20" />
              </div>
              <blockquote className="text-lg font-serif italic font-medium text-foreground leading-relaxed">
                "{testimonial.quote}"
              </blockquote>
            </ScrollScrubItem>
          ))}
        </div>
      </div>
    </section>
  );
};

export default SocialProof;
