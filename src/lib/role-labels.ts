/**
 * Lista 3, item 1: "Owner"/"Admin"/"Member" are Vocify/HubSpot jargon the Head of
 * Sales never asked for. Everywhere a company role reaches a user, it reads as
 * "Head of Sales" (owner/admin) or "Comercial"/"Rep" (member) instead.
 */

export interface RoleLabelCopy {
  teamRoleHeadOfSales: string;
  teamRoleRep: string;
}

export function commercialRoleLabel(role: string, t: RoleLabelCopy): string {
  return role === "owner" || role === "admin" ? t.teamRoleHeadOfSales : t.teamRoleRep;
}
