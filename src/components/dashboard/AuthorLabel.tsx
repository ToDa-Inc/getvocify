import { cn } from "@/lib/utils";

export function AuthorLabel({
  name,
  className,
}: {
  name?: string | null;
  className?: string;
}) {
  if (!name) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-secondary text-muted-foreground",
        className,
      )}
    >
      {name}
    </span>
  );
}
