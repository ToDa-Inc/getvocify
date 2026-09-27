import type { ProductTranslations } from "./product-catalog.ts";

export type SalesRole = "sdr" | "ae" | "general";

export const SALES_ROLE_OPTIONS: readonly SalesRole[] = ["sdr", "ae", "general"];

type SalesRoleCatalog = Pick<
  ProductTranslations,
  "salesRoleSdr" | "salesRoleAe" | "salesRoleGeneral"
>;

/** Display label for a sales role; unknown values use the general label. */
export function salesRoleLabel(
  value: string | null | undefined,
  catalog: SalesRoleCatalog,
): string {
  if (value === "sdr") return catalog.salesRoleSdr;
  if (value === "ae") return catalog.salesRoleAe;
  return catalog.salesRoleGeneral;
}
