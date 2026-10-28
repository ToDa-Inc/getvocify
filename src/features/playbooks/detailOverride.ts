import { createContext, type ReactNode } from "react";

/**
 * What opens when a call type of the funnel is clicked on the Playbook home, instead of its playbook document. Null in
 * the product; a prototype provides another view to try it in its real place.
 */
export const PlaybookDetailContext = createContext<((key: string) => ReactNode) | null>(null);
