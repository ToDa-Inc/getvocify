import { motion } from "framer-motion";
import { Quote } from "lucide-react";

const testimonials = [
  {
    quote: "I used to spend 45 minutes at end of day doing CRM. Now it takes 5 minutes.",
    author: "Carlos M.",
    role: "Account Executive",
    company: "SaaS Company",
    initials: "CM",
  },
  {
    quote: "My team's CRM compliance went from 60% to 95% in two weeks. It's a game changer.",
    author: "Ana R.",
    role: "Head of Sales",
    company: "Tech Startup",
    initials: "AR",
  },
  {
    quote: "I log deals while walking between meetings. My manager thinks I'm a CRM machine.",
    author: "David L.",
    role: "Field Sales Rep",
    company: "Industrial Logistics",
    initials: "DL",
  },
  {
    quote: "Finally, a tool that actually saves time instead of creating more work.",
    author: "Maria S.",
    role: "Sales Manager",
    company: "Financial Services",
    initials: "MS",
  },
];

const SocialProof = () => {
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
            Elite Sales Teams <span className="font-serif italic font-medium text-beige">Trust Vocify.</span>
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
              <blockquote className="text-lg font-medium text-foreground mb-8 leading-relaxed italic font-serif">
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
