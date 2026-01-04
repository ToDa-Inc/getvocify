
interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

const Logo = ({ className = "", size = "md" }: LogoProps) => {
  const sizeClasses = {
    sm: "h-6",
    md: "h-10",
    lg: "h-14",
  };

  return (
    <div className={`flex items-center ${className}`}>
      <img 
        src="/icons/logo_transparent.png" 
        alt="Vocify" 
        className={`${sizeClasses[size]} w-auto object-contain`}
      />
    </div>
  );
};

export default Logo;
