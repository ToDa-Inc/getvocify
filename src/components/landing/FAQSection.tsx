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
    answer: "Voicfy supports 6 languages: English, Spanish, French, German, Italian, Portuguese. Speak naturally in any language.",
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
  return (
    <section className="py-24 bg-secondary/50 grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Frequently Asked Questions
          </h2>
        </div>

        <div className="max-w-3xl mx-auto">
          <Accordion type="single" collapsible className="space-y-4">
            {faqs.map((faq, index) => (
              <AccordionItem
                key={index}
                value={`item-${index}`}
                className="bg-card rounded-xl border border-border px-6"
              >
                <AccordionTrigger className="text-left font-medium text-foreground hover:no-underline py-5">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="text-muted-foreground pb-5">
                  {faq.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>
    </section>
  );
};

export default FAQSection;
