const WaveformCircle = () => {
  return (
    <div className="absolute inset-8 rounded-full bg-cream-dark/80 flex items-center justify-center">
      <div className="relative w-full h-full flex items-center justify-center">
        {/* Simple sound wave bars */}
        <div className="flex items-center justify-center gap-1">
          {[1, 2, 3, 4, 5, 4, 3, 2, 1].map((height, i) => (
            <div
              key={i}
              className="w-1 bg-beige/60 rounded-full"
              style={{
                height: `${height * 8}px`,
                animation: `soundWave 1.2s ease-in-out ${i * 0.1}s infinite`,
              }}
            />
          ))}
        </div>
        
        {/* Center circle with mic icon */}
        <div className="absolute w-20 h-20 md:w-24 md:h-24 rounded-full bg-beige flex items-center justify-center shadow-medium animate-pulse-wave">
          <svg 
            className="w-8 h-8 md:w-10 md:h-10 text-cream" 
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
