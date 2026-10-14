import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import { blurReveal } from "@/lib/scrollReveal";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const FAQSection = () => {
  const { t } = useLanguage();

  return (
    <section className="relative overflow-hidden bg-background py-28 md:py-36">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <span className="section-label mb-6">06 — {t.faq.label}</span>
            <h2 className="h-display mb-6 text-4xl text-foreground md:text-6xl">
              {t.faq.title1} <span className="accent-serif">{t.faq.title2}</span>
            </h2>
          </motion.div>
        </div>

        <div className="max-w-3xl mx-auto">
          <Accordion type="single" collapsible className="space-y-4">
            {t.faq.items.map((faq: { q: string; a: string }, index: number) => (
              <motion.div key={index} {...blurReveal(index * 0.05, 16, 0.97)}>
                <AccordionItem
                  value={`item-${index}`}
                  className="overflow-hidden rounded-2xl border border-border bg-white px-7 transition-colors duration-300 hover:border-beige/40"
                >
                  <AccordionTrigger className="py-5 text-left text-lg font-medium tracking-tight text-foreground hover:no-underline">
                    {faq.q}
                  </AccordionTrigger>
                  <AccordionContent className="text-muted-foreground pb-6 text-base leading-relaxed">
                    {faq.a}
                  </AccordionContent>
                </AccordionItem>
              </motion.div>
            ))}
          </Accordion>
        </div>
      </div>
    </section>
  );
};

export default FAQSection;
