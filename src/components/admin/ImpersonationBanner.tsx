import { getImpersonation, returnToAdmin } from "@/lib/admin-impersonation";
import { Button } from "@/components/ui/button";

const ImpersonationBanner = () => {
  const meta = getImpersonation();
  if (!meta) return null;

  return (
    <div className="bg-beige/15 border-b border-beige/30 px-6 py-2 flex flex-wrap items-center justify-between gap-3 text-sm">
      <span>
        Viewing as <span className="font-medium text-foreground">{meta.email}</span>
        {meta.fullName ? ` (${meta.fullName})` : ""}
      </span>
      <Button size="sm" variant="outline" onClick={returnToAdmin}>
        Return to admin
      </Button>
    </div>
  );
};

export default ImpersonationBanner;
