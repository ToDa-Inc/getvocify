import { HubSpotMark, SalesforceMark } from "./brand-icons";

/**
 * The CRMs Vocify works with, as greyed-out logos on an overlapping stack that fans out on hover, ending in a "+N more" chip.
 * HubSpot and Salesforce are drawn from their marks; Pipedrive's logo is its wordmark (public/logos/pipedrive.svg).
 */
const CrmStack = ({ more, tone = "dark" }: { more: string; tone?: "dark" | "light" }) => {
  const dark = tone === "dark";
  const chip = dark ? "border-white/15 bg-ink text-cream/45 hover:text-cream/80" : "border-border bg-white text-foreground/45 shadow-soft hover:text-foreground/80";
  const accent = dark ? "border-beige/50 bg-beige text-ink" : "border-beige/40 bg-beige text-cream";
  const shared = "-ml-5 flex h-12 items-center rounded-full border text-sm tracking-tight transition-all duration-500 ease-silk group-hover:ml-2";
  const wordmark = dark ? "brightness-0 invert opacity-45" : "brightness-0 opacity-45";

  const logos = [
    <span key="hubspot" className="flex items-center gap-2">
      <HubSpotMark className="h-4 w-4" />
      HubSpot
    </span>,
    <span key="salesforce" className="flex items-center gap-2">
      <SalesforceMark className="h-5 w-5" />
      Salesforce
    </span>,
    <img key="pipedrive" src="/logos/pipedrive.svg" alt="Pipedrive" className={`h-3.5 w-auto ${wordmark}`} />,
  ];

  return (
    <ul className="group flex items-center justify-center">
      {logos.map((logo, i) => (
        <li
          key={i}
          style={{ zIndex: logos.length - i }}
          className={`${shared} px-6 font-medium first:ml-0 group-hover:first:ml-0 ${chip}`}
        >
          {logo}
        </li>
      ))}
      <li className={`${shared} px-5 font-semibold ${accent}`}>{more}</li>
    </ul>
  );
};

export default CrmStack;
