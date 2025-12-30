import { X } from "lucide-react";
import { motion } from "framer-motion";

const painPoints = [
  "Sitting in your car after meetings, frantically typing notes before you forget",
  "End-of-day CRM catch-up when you just want to go home",
  'Incomplete records because you "forgot to log it"',
  '"Why isn\'t your CRM updated?" — Manager',
  "Lost deals because you missed a follow-up you never wrote down",
];

const ProblemSection = () => {
  return (
    <section className="py-32 bg-secondary/20 relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-4xl mx-auto">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center mb-16"
          >
            <h2 className="text-3xl md:text-5xl font-bold text-foreground mb-6 tracking-tight text-balance">
              You're Wasting <span className="font-serif italic font-medium text-beige">5+ Hours Every Week</span> on This:
            </h2>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div className="space-y-4">
              {painPoints.map((point, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: index * 0.1 }}
                  className="flex items-start gap-4 p-5 rounded-2xl bg-white shadow-soft border border-destructive/5 hover:border-destructive/20 transition-colors"
                >
                  <div className="flex-shrink-0 w-6 h-6 rounded-full bg-destructive/10 flex items-center justify-center mt-0.5">
                    <X className="w-4 h-4 text-destructive" />
                  </div>
                  <p className="text-foreground font-medium leading-relaxed">{point}</p>
                </motion.div>
              ))}
            </div>

            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.7 }}
              className="relative p-10 rounded-[3rem] bg-beige text-cream shadow-large overflow-hidden"
            >
              <div className="relative z-10">
                <h3 className="text-2xl font-bold mb-6 italic font-serif">The bottom line:</h3>
                <p className="text-lg leading-relaxed mb-6 opacity-90">
                  Your manager thinks you're not working. Your pipeline is a mess. And you're spending <span className="underline decoration-cream/30 underline-offset-4 font-medium">selling time</span> doing admin work.
                </p>
                <div className="flex items-center gap-4 pt-6 border-t border-cream/20">
                  <div className="w-12 h-12 rounded-full bg-cream/20 flex items-center justify-center">
                    <span className="text-xl font-bold">!</span>
                  </div>
                  <p className="text-xs font-bold uppercase tracking-widest opacity-80">
                    Average revenue loss: $12,400 / year / rep
                  </p>
                </div>
              </div>
              
              {/* Decorative circle */}
              <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-cream/10 rounded-full blur-3xl" />
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ProblemSection;
