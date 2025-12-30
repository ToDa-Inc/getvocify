import { motion } from "framer-motion";

const phrases = [
  "Save 5 hours per week",
  "Never miss a detail", 
  "Update CRM while driving",
  "Perfect for field sales"
];

const RotatingText = () => {
  const text = phrases.join(" • ") + " • ";
  
  return (
    <motion.div 
      initial={{ rotate: 0 }}
      animate={{ rotate: 360 }}
      transition={{ 
        duration: 30, 
        repeat: Infinity, 
        ease: "linear" 
      }}
      whileHover={{ scale: 1.05 }}
      className="absolute inset-0 z-10"
    >
      <svg viewBox="0 0 300 300" className="w-full h-full">
        <defs>
          <path
            id="circlePath"
            d="M 150, 150 m -130, 0 a 130,130 0 1,1 260,0 a 130,130 0 1,1 -260,0"
          />
        </defs>
        <text className="text-[10px] fill-beige/60 font-bold tracking-[0.2em] uppercase">
          <textPath href="#circlePath" startOffset="0%">
            {text}{text}
          </textPath>
        </text>
      </svg>
    </motion.div>
  );
};

export default RotatingText;
