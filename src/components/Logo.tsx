interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  /** On a dark surface the dark wordmark would vanish: keep the bubble as drawn and turn only the wordmark white. */
  onDark?: boolean;
}

/** In logo_transparent.png the bubble ends at about 39% of the width and the wordmark starts at about 44%. */
const BUBBLE_END = "41%";

const Logo = ({ className = "", size = "md", onDark = false }: LogoProps) => {
  const sizeClasses = {
    sm: "h-6",
    md: "h-10",
    lg: "h-14",
  };
  const src = "/icons/logo_transparent.png";
  const imgClass = `${sizeClasses[size]} w-auto object-contain`;

  return (
    <div className={`flex items-center ${className}`}>
      {onDark ? (
        <span className="relative inline-flex" role="img" aria-label="Vocify">
          <img src={src} alt="" className={imgClass} style={{ clipPath: `inset(0 calc(100% - ${BUBBLE_END}) 0 0)` }} />
          <img
            src={src}
            alt=""
            aria-hidden
            className={`${imgClass} absolute inset-0 brightness-0 invert`}
            style={{ clipPath: `inset(0 0 0 ${BUBBLE_END})` }}
          />
        </span>
      ) : (
        <img src={src} alt="Vocify" className={imgClass} />
      )}
    </div>
  );
};

export default Logo;
