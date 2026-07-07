/**
 * Scroll reveal recipes matched to autosetter.ai's real choreography (extracted via
 * live scroll-sweep + getComputedStyle diffing): opacity 0→1, scale ~0.85→1,
 * translateY 30-50px→0, filter blur(12px)→blur(0), values interpolated smoothly
 * rather than snapping — not a plain fade+slide.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

export const blurReveal = (delay = 0, y = 24, scale = 0.94) => ({
  initial: { opacity: 0, y, scale, filter: "blur(10px)" },
  whileInView: { opacity: 1, y: 0, scale: 1, filter: "blur(0px)" },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.8, delay, ease: EASE },
});

/** Card-grid entrance where items fan out from a common origin (rotate + offset) then settle flat — mirrors the testimonial-card stagger on the reference site. */
const fanOffsets = [
  { x: -28, rotate: -6 },
  { x: 0, rotate: 0 },
  { x: 28, rotate: 6 },
  { x: -18, rotate: -4 },
];

export const fanReveal = (index: number, delay = 0) => {
  const o = fanOffsets[index % fanOffsets.length];
  return {
    initial: { opacity: 0, y: 44, x: o.x, rotate: o.rotate, scale: 0.9, filter: "blur(10px)" },
    whileInView: { opacity: 1, y: 0, x: 0, rotate: 0, scale: 1, filter: "blur(0px)" },
    viewport: { once: true, margin: "-80px" },
    transition: { duration: 0.9, delay, ease: EASE },
  };
};
