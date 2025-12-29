import { Mic } from "lucide-react";

interface LogoProps {
  className?: string;
  showText?: boolean;
  size?: "sm" | "md" | "lg";
}

const Logo = ({ className = "", showText = true, size = "md" }: LogoProps) => {
  const sizeClasses = {
    sm: "h-6 w-6",
    md: "h-8 w-8",
    lg: "h-10 w-10",
  };

  const textSizeClasses = {
    sm: "text-lg",
    md: "text-xl",
    lg: "text-2xl",
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className={`${sizeClasses[size]} rounded-xl bg-beige flex items-center justify-center`}>
        <Mic className="h-4 w-4 text-cream" />
      </div>
      {showText && (
        <span className={`font-semibold text-foreground ${textSizeClasses[size]}`}>
          Vocify
        </span>
      )}
    </div>
  );
};

export default Logo;
