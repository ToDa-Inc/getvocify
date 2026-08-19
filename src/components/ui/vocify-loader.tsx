import { cn } from "@/lib/utils";

type VocifyLoaderProps = {
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
};

const sizeClasses = {
  sm: "h-6 gap-[3px] [&_span]:w-[3px]",
  md: "h-9 gap-[5px] [&_span]:w-1",
  lg: "h-12 gap-[5px] [&_span]:w-1",
};

/** Extension-style live bar loader (matches chrome-extension `.live-loader`). */
export function VocifyLoader({ size = "md", className, label }: VocifyLoaderProps) {
  return (
    <div className={cn("flex flex-col items-center gap-3", className)} role="status" aria-live="polite">
      <div
        className={cn(
          "flex items-end justify-center motion-reduce:[&_span]:animate-none motion-reduce:[&_span]:h-4 motion-reduce:[&_span]:opacity-55",
          sizeClasses[size],
        )}
        aria-hidden="true"
      >
        {Array.from({ length: 5 }).map((_, i) => (
          <span
            key={i}
            className="block h-3 rounded-full bg-beige origin-bottom animate-vocify-bar"
            style={{ animationDelay: `${i * 0.08}s` }}
          />
        ))}
      </div>
      {label ? <p className="text-[10px] font-medium text-muted-foreground/60">{label}</p> : null}
    </div>
  );
}

type VocifySpinnerProps = {
  className?: string;
  size?: number;
};

/** Extension-style circular spinner (matches chrome-extension `.mini-spinner`). */
export function VocifySpinner({ className, size = 12 }: VocifySpinnerProps) {
  return (
    <span
      className={cn(
        "inline-block shrink-0 rounded-full border-[1.5px] border-foreground/10 border-t-beige animate-spin motion-reduce:animate-none",
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  );
}
