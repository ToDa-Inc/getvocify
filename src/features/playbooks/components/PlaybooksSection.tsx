import { useState } from "react";
import { useAuth } from "@/features/auth";
import { PlaybookSetupNotice } from "@/features/playbooks/components/PlaybookSetupNotice";
import { playbookNotice, type MotionStatus, type PlaybookRole } from "@/lib/playbook-setup";

const MOTIONS = ["discovery", "qualification", "closing"] as const;

function roleOf(value: string | null | undefined): PlaybookRole {
  if (value === "owner" || value === "admin" || value === "member") return value;
  return "member";
}

export default function PlaybooksSection() {
  const { user } = useAuth();
  const role = roleOf(user?.company?.role);
  const [motions, setMotions] = useState<Record<string, MotionStatus>>({
    discovery: "missing",
    qualification: "missing",
    closing: "missing",
  });
  const notice = playbookNotice(role, motions);

  return (
    <div>
      <h2 className="text-lg font-medium mb-2">Proceso comercial</h2>
      <PlaybookSetupNotice role={role} motions={motions} />
      <ul className="space-y-3">
        {MOTIONS.map((key) => (
          <li key={key} className="flex items-center justify-between gap-3 rounded-xl border border-border px-4 py-3">
            <span className="capitalize">{key}</span>
            <span className="text-sm text-muted-foreground">{motions[key]}</span>
            {notice.canEdit ? (
              <button
                type="button"
                className="rounded-full border border-border px-3 py-1 text-sm"
                onClick={() =>
                  setMotions((current) => ({
                    ...current,
                    [key]: current[key] === "published" ? "missing" : "published",
                  }))
                }
              >
                {motions[key] === "published" ? "Volver a borrador" : "Publicar"}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
