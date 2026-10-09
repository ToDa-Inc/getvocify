import { forwardRef, useImperativeHandle, useMemo, useRef, type CSSProperties } from "react";
import { animIconAttrs, animIconSvg, playAnimIcon, type AnimIconName } from "@shared/ui/components/anim-icon.js";
import { renderToString } from "@shared/ui/html.js";
import { cn } from "@/lib/utils";

export type { AnimIconName };
export type AnimIconHandle = { play: (play?: string) => void };

type AnimIconProps = {
  name: AnimIconName;
  size?: number;
  /** Match the neighbours: the app draws Lucide at 1.5 for its thin look, 2 where it keeps the default. */
  stroke?: number;
  /** Held state: refresh "busy", copy "done", phone "ringing". */
  state?: string | false | null;
  label?: string;
  className?: string;
};

/** The shared moving icon (shared/ui/components/anim-icon.js), same markup as extension and desktop. */
export const AnimIcon = forwardRef<AnimIconHandle, AnimIconProps>(function AnimIcon(
  { name, size = 16, stroke, state, label, className },
  ref,
) {
  const el = useRef<HTMLSpanElement>(null);
  useImperativeHandle(ref, () => ({ play: (play = "ring") => playAnimIcon(el.current, play) }), []);
  // The svg string stays stable across state changes, so React never repaints it mid-animation.
  const svg = useMemo(() => ({ __html: renderToString(animIconSvg(name)) }), [name]);
  const attrs = animIconAttrs(name, { size, stroke, state: state || "" });
  const style = Object.fromEntries(
    attrs.style.split(";").map((pair) => pair.split(":") as [string, string]),
  ) as CSSProperties;
  return (
    <span
      ref={el}
      className={cn(attrs.className, className)}
      style={style}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
      dangerouslySetInnerHTML={svg}
    />
  );
});
