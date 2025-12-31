import { motion } from "framer-motion";
import { Quote } from "lucide-react";

import { useLanguage } from "@/lib/i18n";

const SocialProof = () => {
  const { t } = useLanguage();

  const testimonials = [
    {
      quote: t.socialProof.q1,
      author: "Carlos M.",
      role: "Account Executive",
      company: "SaaS Company",
      initials: "CM",
    },
    {
      quote: t.socialProof.q2,
      author: "Ana R.",
      role: "Head of Sales",
      company: "Tech Startup",
      initials: "AR",
    },
    {
      quote: t.socialProof.q3,
      author: "David L.",
      role: "Field Sales Rep",
      company: "Industrial Logistics",
      initials: "DL",
    },
    {
      quote: t.socialProof.q4,
      author: "Maria S.",
      role: "Sales Manager",
      company: "Financial Services",
      initials: "MS",
    },
  ];

  return (
    <section className="py-32 bg-secondary/30 relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl md:text-5xl font-bold text-foreground mb-6 tracking-tight">
            {t.socialProof.title1} <span className="text-beige font-black">{t.socialProof.title2}</span>
          </h2>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto">
          {testimonials.map((testimonial, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              className="bg-white rounded-[2rem] p-8 shadow-soft border border-border/50 flex flex-col hover:shadow-medium transition-all"
            >
              <div className="mb-6">
                <Quote className="w-10 h-10 text-beige/20" />
              </div>
              <blockquote className="text-lg font-bold text-foreground mb-8 leading-relaxed">
                "{testimonial.quote}"
              </blockquote>
              <div className="mt-auto flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-beige/10 flex items-center justify-center border border-beige/20">
                  <span className="text-sm font-bold text-beige">{testimonial.initials}</span>
                </div>
                <div>
                  <p className="font-bold text-foreground">{testimonial.author}</p>
                  <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                    {testimonial.role} • {testimonial.company}
                  </p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default SocialProof;
