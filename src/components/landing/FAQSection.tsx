import { motion } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const faqs = [
  {
    question: "Does this work with my CRM?",
    answer: "Yes. We support HubSpot, Salesforce, and Pipedrive today. More integrations coming soon. Need something specific? Let us know.",
  },
  {
    question: "How accurate is the AI?",
    answer: "85-90% accuracy out of the box. You always review before it updates your CRM. Over time, it learns your terminology and gets even better.",
  },
  {
    question: "What if I speak Spanish/French/German?",
    answer: "Vocify supports 6 languages: English, Spanish, French, German, Italian, Portuguese. Speak naturally in any language.",
  },
  {
    question: "Is my data secure?",
    answer: "Yes. GDPR compliant. Data stored in EU. Encrypted in transit and at rest. We never sell or share your data. SOC 2 Type II certification in progress.",
  },
  {
    question: "Can I edit before it updates my CRM?",
    answer: "Absolutely. You review and approve every update. Edit anything before it goes to your CRM.",
  },
  {
    question: 'What if I say "um" and "uh" a lot?',
    answer: "Our AI removes filler words automatically. Just talk naturally.",
  },
  {
    question: "Do I need to use specific commands?",
    answer: 'No. Just speak naturally. "Met with John at ABC Corp. He wants a demo next week." That\'s it.',
  },
  {
    question: "Can my manager see my notes?",
    answer: "Only what's in your CRM (same as now). We don't share voice recordings with anyone.",
  },
  {
    question: "What's the free trial?",
    answer: "14 days, unlimited voice memos. No credit card required. Full access to all features.",
  },
  {
    question: "Can I cancel anytime?",
    answer: "Yes. Cancel anytime. No contracts. No cancellation fees.",
  },
];

const FAQSection = () => {
  const { t } = useLanguage();

  return (
    <section className="py-32 bg-secondary/20 relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <motion.h2 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-3xl md:text-5xl font-bold text-foreground mb-6 tracking-tight"
          >
            {t.faq.title1} <span className="font-serif italic font-medium text-beige">{t.faq.title2}</span>
          </motion.h2>
        </div>

        <div className="max-w-3xl mx-auto">
          <Accordion type="single" collapsible className="space-y-4">
            {t.faq.items.map((faq, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.05 }}
              >
                <AccordionItem
                  value={`item-${index}`}
                  className="bg-white/50 backdrop-blur-sm rounded-[2rem] border border-border px-8 overflow-hidden hover:border-beige/30 transition-colors shadow-soft"
                >
                  <AccordionTrigger className="text-left font-bold text-foreground hover:no-underline py-6 text-lg">
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
