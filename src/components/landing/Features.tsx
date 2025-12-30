import { Zap, Target, Shield, Globe, Smartphone, Plug, Users, Edit } from "lucide-react";
import { motion } from "framer-motion";

const features = [
  {
    icon: Zap,
    title: "Instant Processing",
    description: "60-second updates. Not 10 minutes of typing.",
    className: "md:col-span-2 md:row-span-1",
    iconBg: "bg-amber-100",
    iconColor: "text-amber-600",
  },
  {
    icon: Target,
    title: "AI Precision",
    description: "AI understands sales terminology. Extracts deals, contacts, and next steps automatically.",
    className: "md:col-span-1 md:row-span-1",
    iconBg: "bg-blue-100",
    iconColor: "text-blue-600",
  },
  {
    icon: Smartphone,
    title: "Mobile-First",
    description: "Record on your phone between meetings. Syncs everywhere.",
    className: "md:col-span-1 md:row-span-2",
    iconBg: "bg-purple-100",
    iconColor: "text-purple-600",
  },
  {
    icon: Plug,
    title: "CRM Sync",
    description: "Direct integration with HubSpot, Salesforce, and Pipedrive.",
    className: "md:col-span-1 md:row-span-1",
    iconBg: "bg-green-100",
    iconColor: "text-green-600",
  },
  {
    icon: Globe,
    title: "Multi-Language",
    description: "English, Spanish, French, German, Italian, Portuguese.",
    className: "md:col-span-1 md:row-span-1",
    iconBg: "bg-orange-100",
    iconColor: "text-orange-600",
  },
  {
    icon: Shield,
    title: "Enterprise Security",
    description: "GDPR compliant. EU data storage. SOC 2 Type II in progress.",
    className: "md:col-span-2 md:row-span-1",
    iconBg: "bg-slate-100",
    iconColor: "text-slate-600",
  },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.5,
      ease: "easeOut",
    },
  },
};

const Features = () => {
  return (
    <section id="features" className="py-32 bg-background relative overflow-hidden">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-20">
          <motion.h2 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-3xl md:text-5xl font-bold text-foreground mb-6 tracking-tight"
          >
            Everything You Need. <span className="font-serif italic font-medium text-beige">Nothing You Don't.</span>
          </motion.h2>
          <motion.p 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-lg text-muted-foreground max-w-2xl mx-auto"
          >
            Powerful tools designed for elite sales teams who value their time.
          </motion.p>
        </div>

        <motion.div 
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          className="grid grid-cols-1 md:grid-cols-4 gap-6 max-w-6xl mx-auto"
        >
          {features.map((feature) => (
            <motion.div
              key={feature.title}
              variants={itemVariants}
              className={`group glass-morphism p-8 rounded-[2rem] hover-lift transition-all duration-500 ${feature.className}`}
            >
              <div className={`w-14 h-14 rounded-2xl ${feature.iconBg} flex items-center justify-center mb-6 transition-transform duration-500 group-hover:scale-110 group-hover:rotate-3`}>
                <feature.icon className={`w-7 h-7 ${feature.iconColor}`} />
              </div>
              <h3 className="text-xl font-bold text-foreground mb-3 tracking-tight">
                {feature.title}
              </h3>
              <p className="text-muted-foreground leading-relaxed">
                {feature.description}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>

      {/* Background accents */}
      <div className="absolute top-1/2 left-0 w-[500px] h-[500px] bg-beige/5 rounded-full blur-[120px] -z-10" />
      <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-accent/5 rounded-full blur-[120px] -z-10" />
    </section>
  );
};

export default Features;
