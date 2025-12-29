const WaveformCircle = () => {
  const bars = 24;
  
  return (
    <div className="absolute inset-8 rounded-full bg-cream-dark/80 flex items-center justify-center">
      <div className="relative w-full h-full flex items-center justify-center">
        {/* Waveform bars arranged radially */}
        <div className="absolute inset-0">
          {Array.from({ length: bars }).map((_, i) => {
            const angle = (i / bars) * 360;
            const baseHeight = 15 + (Math.sin(i * 0.5) + 1) * 15;
            
            return (
              <div
                key={i}
                className="absolute left-1/2 top-1/2 w-0.5 bg-primary/40 rounded-full origin-bottom"
                style={{
                  height: `${baseHeight}%`,
                  transform: `translate(-50%, -100%) rotate(${angle}deg)`,
                  transformOrigin: '50% 100%',
                  animation: `waveform 1.5s ease-in-out ${i * 0.08}s infinite`,
                }}
              />
            );
          })}
        </div>
        
        {/* Center circle with mic icon */}
        <div className="w-16 h-16 md:w-20 md:h-20 rounded-full bg-primary flex items-center justify-center shadow-medium z-10 animate-pulse-wave">
          <svg 
            className="w-6 h-6 md:w-8 md:h-8 text-primary-foreground" 
            fill="currentColor" 
            viewBox="0 0 24 24"
          >
            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5zm6 6c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
          </svg>
        </div>
      </div>
    </div>
  );
};

export default WaveformCircle;
