import { useRef, useState } from "react";
import { ExternalLink } from "lucide-react";
import { HubSpotMark } from "@/components/dashboard/hubspot/HubSpotMark";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { openExternalLink } from "@/lib/desktop-host";
import { initialsOf, type RowContact } from "@/lib/interactions";
import { useLanguage } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const MAX_VISIBLE = 3;
/** Soft theme tints, so the same person keeps the same circle on every row. */
const TINTS = ["bg-beige/15 text-beige", "bg-success/15 text-success", "bg-secondary text-foreground/80", "bg-muted text-muted-foreground"];

function tintOf(contact: RowContact) {
  const key = (contact.email || contact.name || "").toLowerCase();
  let hash = 0;
  for (const char of key) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TINTS[hash % TINTS.length];
}

function Circle({ contact, className }: { contact: RowContact; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("relative flex shrink-0 items-center justify-center rounded-full text-[10.5px] font-medium", tintOf(contact), className)}
    >
      {initialsOf(contact)}
      {contact.crm ? <HubSpotMark className="absolute -bottom-1 -right-1 h-3.5 w-3.5 ring-2 ring-background group-hover:ring-secondary" /> : null}
    </span>
  );
}

/**
 * The people a row involved, as overlapping initials (up to three, then "+N"). Hovering, focusing or
 * tapping opens the list with names and emails; the contact the CRM knows carries the HubSpot mark and,
 * when the record can be built, a link to it. Sits above the row's own link so it opens on its own.
 */
export function ContactStack({
  contacts,
  kind,
  crmUrl,
  crmName,
}: {
  contacts: RowContact[];
  kind: "meeting" | "single";
  crmUrl: string | null;
  crmName: string;
}) {
  const { t } = useLanguage();
  const copy = t.product.interactions;
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  if (contacts.length === 0) return null;

  const later = (next: boolean, delay: number) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(next), delay);
  };
  const visible = contacts.slice(0, MAX_VISIBLE);
  const overflow = contacts.length - visible.length;
  const heading = kind === "meeting" ? copy.attendees.replace("{n}", String(contacts.length)) : copy.contact;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={heading}
          onMouseEnter={() => later(true, 120)}
          onMouseLeave={() => later(false, 120)}
          className="relative z-10 flex items-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring max-sm:hidden"
        >
          {visible.map((contact, index) => (
            <Circle
              key={`${contact.email ?? contact.name}-${index}`}
              contact={contact}
              className={cn("h-[26px] w-[26px] ring-2 ring-background group-hover:ring-secondary", index > 0 && "-ml-2")}
            />
          ))}
          {overflow > 0 ? (
            <span
              aria-hidden
              className="-ml-2 flex h-[26px] w-[26px] items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground ring-2 ring-background group-hover:ring-secondary"
            >
              +{overflow}
            </span>
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-[21rem] p-1.5"
        onMouseEnter={() => later(true, 0)}
        onMouseLeave={() => later(false, 120)}
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <p className="px-2 pb-1 pt-1.5 text-xs text-muted-foreground">{heading}</p>
        <ul className="max-h-64 overflow-y-auto">
          {contacts.map((contact, index) => {
            const detail = contact.email ?? "";
            const label = contact.name || contact.email || "";
            const link = contact.crm ? crmUrl : null;
            const body = (
              <>
                <Circle contact={contact} className="h-[30px] w-[30px]" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13.5px] text-foreground">{label}</p>
                  {contact.name && detail ? <p className="truncate text-xs text-muted-foreground">{detail}</p> : null}
                </div>
                {link ? (
                  <span className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-lg border border-border/70 pl-1.5 pr-2 text-xs text-foreground/85">
                    <HubSpotMark className="h-4 w-4" />
                    {crmName}
                    <ExternalLink aria-hidden className="h-3 w-3 opacity-60" strokeWidth={1.5} />
                  </span>
                ) : null}
              </>
            );
            const rowClass = "flex items-center gap-2.5 rounded-lg px-2 py-1.5";
            return (
              <li key={`${contact.email ?? contact.name}-${index}`}>
                {link ? (
                  // The whole row opens the CRM record, not only the chip.
                  <a
                    href={link}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(event) => openExternalLink(event, link)}
                    aria-label={`${label}: ${copy.openInCrm.replace("{crm}", crmName)}`}
                    className={cn(rowClass, "transition-colors hover:bg-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none")}
                  >
                    {body}
                  </a>
                ) : (
                  <div className={rowClass}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
