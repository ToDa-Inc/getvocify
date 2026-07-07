import { motion, useScroll, useTransform } from "framer-motion";
import { useRef, type ReactNode } from "react";

/**
 * Genuine scroll-scrubbed reveal — matches autosetter.ai's real technique (confirmed via
 * live scroll-trace: values interpolate continuously with scroll position, never a
 * fixed-duration "trigger once" animation). Opacity/scale/blur/rotate are a pure function
 * of how far the element has travelled through the viewport, so there's no discrete
 * animation-start event that can stutter or double-fire.
 */
const ScrollScrubItem = ({
  children,
  className,
  rotate = 0,
  x = 0,
}: {
  children: ReactNode;
  className?: string;
  rotate?: number;
  x?: number;
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.92", "start 0.55"] });

  const opacity = useTransform(scrollYProgress, [0, 1], [0, 1]);
  const scale = useTransform(scrollYProgress, [0, 1], [0.92, 1]);
  const y = useTransform(scrollYProgress, [0, 1], [40, 0]);
  const xPos = useTransform(scrollYProgress, [0, 1], [x, 0]);
  const rotateVal = useTransform(scrollYProgress, [0, 1], [rotate, 0]);
  const blur = useTransform(scrollYProgress, [0, 1], [10, 0]);
  const filter = useTransform(blur, (v) => `blur(${v}px)`);

  return (
    <motion.div ref={ref} style={{ opacity, scale, y, x: xPos, rotate: rotateVal, filter }} className={className}>
      {children}
    </motion.div>
  );
};

export default ScrollScrubItem;
