import { X, Car, Clock, FileWarning, MessageCircle, TrendingDown, AlertCircle } from "lucide-react";
import { motion, useScroll, useTransform, AnimatePresence } from "framer-motion";
import { useLanguage } from "@/lib/i18n";
import { useRef, useState, useEffect } from "react";

const RollingNumber = ({ value }: { value: number }) => {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    let start = 0;
    const end = value;
    const duration = 2000;
    const startTime = performance.now();

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing function (easeOutExpo)
      const easeProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      
      const current = Math.floor(easeProgress * end);
      setDisplayValue(current);

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    requestAnimationFrame(animate);
  }, [value]);

  return <span>{displayValue.toLocaleString()}</span>;
};

const ProblemSection = () => {
  const { t } = useLanguage();
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredPoint, setHoveredPoint] = useState<number | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const rightCardRef = useRef<HTMLDivElement>(null);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start end", "end start"]
  });

  const lineHeight = useTransform(scrollYProgress, [0.2, 0.5], ["0%", "100%"]);

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!rightCardRef.current) return;
    const rect = rightCardRef.current.getBoundingClientRect();
    setMousePos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  const painPoints = [
    { text: t.problem.p1, icon: Car },
    { text: t.problem.p2, icon: Clock },
    { text: t.problem.p3, icon: FileWarning },
    { text: t.problem.p4, icon: MessageCircle },
    { text: t.problem.p5, icon: TrendingDown },
  ];

  return (
    <section 
      ref={containerRef}
      className="py-32 bg-secondary/20 relative overflow-hidden border-t border-border/50"
    >
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-5xl mx-auto">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="text-center mb-20"
          >
            <h2 className="text-4xl md:text-6xl font-black text-foreground mb-8 tracking-tighter leading-tight text-balance">
              {t.problem.title1} <br />
              <span className="text-beige font-black">{t.problem.title2}</span> {t.problem.title3}
            </h2>
          </motion.div>

          <div className="grid lg:grid-cols-5 gap-12 items-start">
            <div className="lg:col-span-3 relative">
              {/* The "Waste Line" Connector - Aligned to center of icons */}
              <div className="absolute left-[36px] top-8 bottom-8 w-px bg-beige/10 hidden md:block">
                <motion.div 
                  style={{ height: lineHeight }}
                  className="w-full bg-gradient-to-b from-beige/20 via-beige to-beige/20 origin-top shadow-[0_0_15px_rgba(var(--beige),0.5)]"
                />
              </div>

              <div className="space-y-10 relative z-10">
                {painPoints.map((point, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true, margin: "-100px" }}
                    transition={{ duration: 0.5, delay: index * 0.1 }}
                    onMouseEnter={() => setHoveredPoint(index)}
                    onMouseLeave={() => setHoveredPoint(null)}
                    className="flex items-center gap-8 group cursor-default"
                  >
                    {/* The Dot/Icon Hub */}
                    <div className="relative flex-shrink-0">
                      <div className={`w-[72px] h-[72px] rounded-full flex items-center justify-center transition-all duration-700
                        ${hoveredPoint === index 
                          ? "bg-beige text-cream scale-110 shadow-large ring-4 ring-beige/10" 
                          : "bg-white text-beige shadow-soft ring-1 ring-border/50"
                        }`}>
                        <point.icon className="w-7 h-7" />
                      </div>
                      {/* Interaction ripple */}
                      <AnimatePresence>
                        {hoveredPoint === index && (
                          <motion.div 
                            initial={{ scale: 0.8, opacity: 0 }}
                            animate={{ scale: 1.5, opacity: 0.2 }}
                            exit={{ scale: 2, opacity: 0 }}
                            className="absolute inset-0 bg-beige rounded-full -z-10"
                          />
                        )}
                      </AnimatePresence>
                    </div>

                    <div className={`flex-1 p-8 rounded-[2.5rem] transition-all duration-500 will-change-transform
                      ${hoveredPoint === index 
                        ? "bg-white shadow-large -translate-y-1 border-beige/10" 
                        : "bg-white/30 hover:bg-white/50 border-transparent"
                      } border`}>
                      <p className={`text-xl font-bold leading-snug transition-colors duration-500
                        ${hoveredPoint === index ? "text-foreground" : "text-foreground/60"}`}>
                        {point.text}
                      </p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>

            <div className="lg:col-span-2">
              <motion.div 
                ref={rightCardRef}
                onMouseMove={handleMouseMove}
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.8 }}
                className="sticky top-32 relative p-12 md:p-14 rounded-[4rem] bg-white/40 backdrop-blur-xl text-foreground shadow-2xl overflow-hidden group/card border border-white/20 shadow-[inset_4px_4px_8px_rgba(255,255,255,0.8),inset_-4px_-4px_8px_rgba(0,0,0,0.02)]"
              >
                {/* Spotlight Effect */}
                <div 
                  className="absolute inset-0 opacity-0 group-hover/card:opacity-100 transition-opacity duration-700 pointer-events-none"
                  style={{
                    background: `radial-gradient(800px circle at ${mousePos.x}px ${mousePos.y}px, rgba(217,119,6,0.1), transparent 40%)`
                  }}
                />

                <div className="relative z-10 space-y-10">
                  <div className="space-y-4">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-beige/10 border border-beige/20 text-[10px] font-black uppercase tracking-[0.3em] text-beige">
                      <AlertCircle className="w-3 h-3" />
                      Insight
                    </div>
                    <h3 className="text-4xl font-black leading-none tracking-tight text-foreground">
                      {t.problem.bottomLine}
                    </h3>
                  </div>

                  <div className="space-y-8">
                    <p className="text-2xl leading-relaxed text-foreground/90 font-medium tracking-tight">
                      {t.problem.result1}{" "}
                      <span className="relative inline-block px-1">
                        <span className="relative z-10 text-foreground">{t.problem.result2}</span>
                        <motion.svg
                          viewBox="0 0 100 20"
                          className="absolute -bottom-1 left-0 w-full h-4 text-beige/40 -z-0"
                          initial={{ pathLength: 0 }}
                          whileInView={{ pathLength: 1 }}
                          viewport={{ once: true }}
                          transition={{ duration: 1.2, delay: 0.8, ease: "easeInOut" }}
                        >
                          <motion.path
                            d="M2,15 Q50,25 98,15"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="12"
                            strokeLinecap="round"
                          />
                        </motion.svg>
                      </span>{" "}
                      {t.problem.result3}
                    </p>
                  </div>

                  <div className="pt-12 border-t border-foreground/5">
                    <div className="flex flex-col gap-6">
                      <div className="space-y-2">
                        <p className="text-[10px] font-black uppercase tracking-[0.4em] text-muted-foreground/40">
                          {t.problem.drainLabel}
                        </p>
                        <div className="flex flex-wrap items-baseline gap-2">
                          <span className="text-4xl md:text-5xl font-black tracking-tighter text-foreground">
                            €<RollingNumber value={12400} />
                          </span>
                          <span className="text-sm md:text-xl font-bold text-muted-foreground/40">
                            {t.problem.perYearRep}
                          </span>
                        </div>
                      </div>
                      
                      <div className={`p-6 rounded-3xl bg-beige/5 border border-beige/10 transition-all duration-700
                        ${hoveredPoint !== null ? "bg-beige/10 border-beige/30" : ""}`}>
                        <div className="flex items-start gap-4">
                          <div className="w-10 h-10 rounded-full bg-beige/10 flex items-center justify-center flex-shrink-0">
                            <TrendingDown className="w-5 h-5 text-beige" />
                          </div>
                          <p className="text-xs font-bold leading-tight text-muted-foreground/80">
                            {t.problem.drainNote}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                {/* Decorative background shape */}
                <div className={`absolute -bottom-20 -right-20 w-80 h-80 bg-beige/5 rounded-full blur-[100px] transition-all duration-1000
                  ${hoveredPoint !== null ? "scale-150 opacity-20" : "scale-100 opacity-5"}`} />
              </motion.div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ProblemSection;
