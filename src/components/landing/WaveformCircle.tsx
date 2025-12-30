import { motion } from "framer-motion";
import { Mic } from "lucide-react";

const WaveformCircle = () => {
  const bars = [1, 2, 3, 4, 5, 4, 3, 2, 1, 2, 3, 4, 3, 2, 1];
  
  return (
    <div className="absolute inset-8 rounded-full bg-white/40 backdrop-blur-sm flex items-center justify-center border border-white/20 shadow-medium overflow-hidden group">
      <div className="relative w-full h-full flex items-center justify-center">
        {/* Animated sound wave bars */}
        <div className="flex items-center justify-center gap-1.5 h-32">
          {bars.map((height, i) => (
            <motion.div
              key={i}
              initial={{ height: 10 }}
              animate={{ 
                height: [10, height * 12, 10],
              }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                delay: i * 0.1,
                ease: "easeInOut"
              }}
              className="w-1.5 bg-beige/40 rounded-full group-hover:bg-beige/60 transition-colors"
            />
          ))}
        </div>
        
        {/* Center circle with mic icon */}
        <motion.div 
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="absolute w-24 h-24 md:w-28 md:h-28 rounded-full bg-beige flex items-center justify-center shadow-large cursor-pointer z-20"
        >
          <div className="absolute inset-0 rounded-full bg-beige animate-ping opacity-20" />
          <Mic className="w-10 h-10 md:w-12 md:h-12 text-cream" />
        </motion.div>

        {/* Floating particles for depth */}
        <motion.div 
          animate={{ 
            y: [0, -10, 0],
            opacity: [0.3, 0.6, 0.3]
          }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-1/4 right-1/4 w-2 h-2 bg-beige/30 rounded-full blur-sm"
        />
        <motion.div 
          animate={{ 
            y: [0, 10, 0],
            opacity: [0.2, 0.5, 0.2]
          }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", delay: 1 }}
          className="absolute bottom-1/4 left-1/4 w-3 h-3 bg-accent/20 rounded-full blur-sm"
        />
      </div>
    </div>
  );
};

export default WaveformCircle;
