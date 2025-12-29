interface SimpleWaveformProps {
  isRecording: boolean;
  isProcessing: boolean;
}

const SimpleWaveform = ({ isRecording, isProcessing }: SimpleWaveformProps) => {
  const bars = 9;
  const heights = [1, 2, 3, 4, 5, 4, 3, 2, 1];
  
  return (
    <div className="flex items-center justify-center gap-1.5">
      {heights.map((baseHeight, i) => (
        <div
          key={i}
          className={`w-1.5 rounded-full transition-all duration-300 ${
            isRecording 
              ? "bg-destructive" 
              : isProcessing 
                ? "bg-beige" 
                : "bg-muted-foreground/30"
          }`}
          style={{
            height: isRecording || isProcessing 
              ? `${baseHeight * 10}px` 
              : `${baseHeight * 6}px`,
            animation: isRecording 
              ? `soundWave 0.8s ease-in-out ${i * 0.08}s infinite` 
              : isProcessing 
                ? `pulse 1.5s ease-in-out ${i * 0.1}s infinite` 
                : "none",
          }}
        />
      ))}
    </div>
  );
};

export default SimpleWaveform;
