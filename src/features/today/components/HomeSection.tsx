import { useId, type ReactNode } from "react";
import { THEME_TOKENS } from "@/lib/theme/tokens";

export function HomeSection({ title, children }: { title: string; children?: ReactNode }) {
  const id = useId();
  if (children == null || children === false) return null;
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className={`mx-0.5 mb-2.5 ${THEME_TOKENS.typography.capsLabel}`}>{title}</h2>
      {children}
    </section>
  );
}
