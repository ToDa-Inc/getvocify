import { createContext, useContext } from "react";

/**
 * The dashboard's single right column. On the rep home (flag on, /dashboard) it holds the
 * contact panel; Ask takes its place while open.
 */
export type HomeColumn = {
  target: HTMLElement | null;
  askOpen: boolean;
  closeAsk: () => void;
  canDial: boolean;
};

export const HomeColumnContext = createContext<HomeColumn | null>(null);

export function useHomeColumn(): HomeColumn | null {
  return useContext(HomeColumnContext);
}
