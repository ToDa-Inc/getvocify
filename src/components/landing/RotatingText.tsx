const phrases = [
  "Save 5 hours per week",
  "Never miss a detail", 
  "Update CRM while driving",
  "Perfect for field sales"
];

const RotatingText = () => {
  const totalChars = phrases.join(" • ").length + (phrases.length * 3);
  const text = phrases.join(" • ") + " • ";
  
  return (
    <div className="absolute inset-0 animate-rotate-slow">
      <svg viewBox="0 0 300 300" className="w-full h-full">
        <defs>
          <path
            id="circlePath"
            d="M 150, 150 m -120, 0 a 120,120 0 1,1 240,0 a 120,120 0 1,1 -240,0"
          />
        </defs>
        <text className="text-[11px] fill-muted-foreground font-medium tracking-widest uppercase">
          <textPath href="#circlePath" startOffset="0%">
            {text}{text}
          </textPath>
        </text>
      </svg>
    </div>
  );
};

export default RotatingText;
