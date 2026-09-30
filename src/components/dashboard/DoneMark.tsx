import { useMemo } from "react";
import { renderDoneMark } from "@shared/ui/components/done-mark.js";
import { renderToString } from "@shared/ui/html.js";

/** The shared "it's in your CRM" mark (shared/ui/components/done-mark.js), same as extension and desktop. */
export function DoneMark({
  tone = "success",
  size = 64,
  animate = true,
  label = "",
  className = "",
}: {
  tone?: "success" | "failed";
  size?: number;
  animate?: boolean;
  label?: string;
  className?: string;
}) {
  const markup = useMemo(
    () => renderToString(renderDoneMark({ tone, size, animate, label })),
    [tone, size, animate, label],
  );
  return <span className={`inline-flex ${className}`} dangerouslySetInnerHTML={{ __html: markup }} />;
}
