import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import {
  crmKeys,
  fieldPermissionsApi,
  SESSION_QUERY_STALE_MS,
  type CRMConfiguration,
  type FieldListKey,
  type FieldLists,
  type FieldPermissionMember,
  type FieldPermissionRole,
} from "@/lib/api/crm";
import { DEFAULT_HUBSPOT_CONFIG, loadHubSpotSetup, type HubSpotObjectTab } from "@/lib/api/hubspot-setup";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const OBJECTS: { id: HubSpotObjectTab; key: FieldListKey; label: string }[] = [
  { id: "deals", key: "allowed_deal_fields", label: "Deals" },
  { id: "contacts", key: "allowed_contact_fields", label: "Contacts" },
  { id: "companies", key: "allowed_company_fields", label: "Companies" },
  { id: "line_items", key: "allowed_line_item_fields", label: "Line items" },
];

const ROLES: FieldPermissionRole[] = ["sdr", "ae", "general"];
const ROLE_LABEL_KEYS = {
  sdr: "teamMemberTypeSdr",
  ae: "teamMemberTypeAe",
  general: "teamMemberTypeGeneral",
} as const;

const EMPTY_LISTS: FieldLists = {
  allowed_deal_fields: null,
  allowed_contact_fields: null,
  allowed_company_fields: null,
  allowed_line_item_fields: null,
};

type Scope = { kind: "role"; role: FieldPermissionRole } | { kind: "member"; userId: string };

function isManager(role: string) {
  return role === "owner" || role === "admin";
}

/** The role whose lists a person inherits; null = the company's (a Head of Sales with no type). */
function inheritedRole(member: FieldPermissionMember, salesRolesOn: boolean): FieldPermissionRole | null {
  if (!salesRolesOn) return null;
  if (member.sales_role) return member.sales_role;
  return isManager(member.role) ? null : "general";
}

/** Per role, then per person: which HubSpot fields the AI fills for their calls. Pipeline,
 * stages, Skip Approve and create contacts/companies stay the company's (the form above). */
export const HubSpotFieldPermissions = () => {
  const { t } = useLanguage();
  const p = t.product;
  const queryClient = useQueryClient();
  const setup = useQuery({
    queryKey: crmKeys.hubspotSetup(),
    queryFn: () => loadHubSpotSetup(false),
    staleTime: SESSION_QUERY_STALE_MS,
  });
  const perms = useQuery({
    queryKey: crmKeys.fieldPermissions(),
    queryFn: () => fieldPermissionsApi.get(),
  });

  const salesRolesOn = perms.data?.sales_roles_enabled ?? false;
  const members = perms.data?.members ?? [];
  const [scope, setScope] = useState<Scope | null>(null);
  const [draft, setDraft] = useState<FieldLists | null>(null);
  const [activeObject, setActiveObject] = useState<HubSpotObjectTab>("deals");
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);

  const activeScope: Scope | null =
    scope ??
    (salesRolesOn
      ? { kind: "role", role: "sdr" }
      : members[0]
        ? { kind: "member", userId: members[0].user_id }
        : null);

  const company: CRMConfiguration = setup.data?.config ?? DEFAULT_HUBSPOT_CONFIG;
  const companyLists: Record<FieldListKey, string[]> = {
    allowed_deal_fields: company.allowed_deal_fields ?? [],
    allowed_contact_fields: company.allowed_contact_fields ?? [],
    allowed_company_fields: company.allowed_company_fields ?? [],
    allowed_line_item_fields: company.allowed_line_item_fields ?? [],
  };

  const member =
    activeScope?.kind === "member" ? members.find((m) => m.user_id === activeScope.userId) ?? null : null;
  const stored: FieldLists =
    (activeScope?.kind === "role"
      ? perms.data?.roles[activeScope.role]
      : member?.fields) ?? EMPTY_LISTS;
  const current: FieldLists = draft ?? stored;

  const parentRole = member ? inheritedRole(member, salesRolesOn) : null;
  const parentLists = (key: FieldListKey): string[] => {
    if (activeScope?.kind === "member" && parentRole) {
      const roleLists = perms.data?.roles[parentRole];
      if (roleLists?.[key] != null) return roleLists[key] as string[];
    }
    return companyLists[key];
  };
  const parentLabel =
    activeScope?.kind === "member" && parentRole ? p[ROLE_LABEL_KEYS[parentRole]] : p.fieldPermsCompany;

  const objectMeta = OBJECTS.find((o) => o.id === activeObject)!;
  const own = current[objectMeta.key];
  const inherits = own === null;
  const shown = inherits ? parentLists(objectMeta.key) : own;
  const schema = setup.data?.schemas[activeObject];

  // No search: this scope's fields first, then the ones it would inherit. A search reaches
  // any HubSpot property, so a role can fill a field the company list does not.
  const properties = schema?.properties ?? [];
  const labelOf = (name: string) => properties.find((prop) => prop.name === name)?.label ?? name;
  const query = search.trim().toLowerCase();
  const candidates = query
    ? properties
        .filter((prop) => prop.label.toLowerCase().includes(query) || prop.name.toLowerCase().includes(query))
        .slice(0, 60)
        .map((prop) => ({ name: prop.name, label: prop.label }))
    : [...shown, ...parentLists(objectMeta.key).filter((n) => !shown.includes(n))].map((name) => ({
        name,
        label: labelOf(name),
      }));

  const pickScope = (next: Scope) => {
    setScope(next);
    setDraft(null);
    setSearch("");
  };

  const setOwn = (value: string[] | null) =>
    setDraft({ ...current, [objectMeta.key]: value });

  const toggle = (name: string) => {
    if (inherits) return;
    setOwn(own!.includes(name) ? own!.filter((n) => n !== name) : [...own!, name]);
  };

  const refresh = () => queryClient.invalidateQueries({ queryKey: crmKeys.fieldPermissions() });

  const save = async () => {
    if (!activeScope || !draft) return;
    setSaving(true);
    try {
      if (activeScope.kind === "role") await fieldPermissionsApi.saveRole(activeScope.role, draft);
      else await fieldPermissionsApi.saveMember(activeScope.userId, draft);
      await refresh();
      setDraft(null);
      toast.success(p.fieldPermsSaved);
    } catch {
      toast.error(p.fieldPermsSaveFailed);
    } finally {
      setSaving(false);
    }
  };

  const resetAll = async () => {
    if (!activeScope) return;
    setSaving(true);
    try {
      if (activeScope.kind === "role") await fieldPermissionsApi.resetRole(activeScope.role);
      else await fieldPermissionsApi.resetMember(activeScope.userId);
      await refresh();
      setDraft(null);
      toast.success(p.fieldPermsSaved);
    } catch {
      toast.error(p.fieldPermsSaveFailed);
    } finally {
      setSaving(false);
    }
  };

  if (perms.isLoading || setup.isLoading) {
    return (
      <div className="flex justify-center py-6">
        <VocifySpinner size={16} />
      </div>
    );
  }
  if (perms.isError || !activeScope) {
    return <p className="text-sm text-muted-foreground">{perms.isError ? p.fieldPermsLoadFailed : p.fieldPermsNoMembers}</p>;
  }

  const hasOwnLists = Object.values(stored).some((v) => v !== null);
  const scopeName =
    activeScope.kind === "role"
      ? p[ROLE_LABEL_KEYS[activeScope.role]]
      : member?.full_name || member?.email || "";
  const chip = (active: boolean) =>
    `px-3 py-1.5 rounded-full text-[12px] border transition-all ${
      active
        ? "bg-beige/15 border-beige/40 text-beige"
        : "bg-secondary/5 border-border/30 text-muted-foreground hover:border-border/50"
    }`;

  return (
    <div className="space-y-5" data-testid="field-permissions">
      <div>
        <h4 className={THEME_TOKENS.typography.capsLabel}>{p.fieldPermsTitle}</h4>
        <p className="text-xs text-muted-foreground mt-1">{p.fieldPermsHelper}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {salesRolesOn &&
          ROLES.map((role) => {
            const custom = perms.data?.roles[role] != null;
            return (
              <button
                key={role}
                type="button"
                className={chip(activeScope.kind === "role" && activeScope.role === role)}
                onClick={() => pickScope({ kind: "role", role })}
              >
                {p[ROLE_LABEL_KEYS[role]]}
                {custom && <span className="ml-1.5 opacity-60">•</span>}
              </button>
            );
          })}
        {members.length > 0 && (
          <div className="relative">
            <select
              aria-label={p.fieldPermsPerson}
              value={activeScope.kind === "member" ? activeScope.userId : ""}
              onChange={(e) => e.target.value && pickScope({ kind: "member", userId: e.target.value })}
              className="h-8 pl-3 pr-8 rounded-full border border-border/40 bg-secondary/5 text-[12px] text-foreground appearance-none cursor-pointer focus:outline-none"
            >
              <option value="">{p.fieldPermsPerson}</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {(m.full_name || m.email) + (m.fields ? " •" : "")}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/40 pointer-events-none" />
          </div>
        )}
      </div>
      {!salesRolesOn && <p className="text-xs text-muted-foreground">{p.fieldPermsRolesOff}</p>}

      <div className="rounded-2xl border border-border/20 bg-secondary/5 p-4 space-y-4">
        <p className="text-[13px] text-foreground">
          {p.fieldPermsEditing.replace("{name}", scopeName)}
        </p>

        <div className="flex flex-wrap gap-2">
          {OBJECTS.map((o) => {
            const value = current[o.key];
            return (
              <button
                key={o.id}
                type="button"
                className={chip(activeObject === o.id)}
                onClick={() => {
                  setActiveObject(o.id);
                  setSearch("");
                }}
              >
                {o.label}
                <span className="ml-2 opacity-50">{value === null ? p.fieldPermsInheritsShort : value.length}</span>
              </button>
            );
          })}
        </div>

        {inherits ? (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
            <p className="text-xs text-muted-foreground">
              {p.fieldPermsInherits.replace("{parent}", parentLabel)} ({shown.length})
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="rounded-full h-8 px-3 text-[12px] border-border/50 text-beige"
              onClick={() => setOwn([...parentLists(objectMeta.key)])}
            >
              {p.fieldPermsCustomize.replace("{name}", scopeName)}
            </Button>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
              <Input
                placeholder={p.fieldPermsSearch}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="bg-background border-border/40 rounded-full pl-10 h-9"
              />
            </div>
            <button
              type="button"
              className="text-[12px] text-muted-foreground underline underline-offset-2"
              onClick={() => setOwn(null)}
            >
              {p.fieldPermsBackToInherit.replace("{parent}", parentLabel)}
            </button>
          </div>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {candidates.map((c) => {
            const on = shown.includes(c.name);
            return (
              <button
                key={c.name}
                type="button"
                aria-pressed={on}
                disabled={inherits}
                onClick={() => toggle(c.name)}
                className={`flex items-center justify-between px-3 py-2 rounded-xl border text-left transition-all ${
                  on ? "bg-beige/10 border-beige/30 text-beige" : "bg-background border-border/20 text-muted-foreground"
                } ${inherits ? "opacity-70 cursor-default" : "hover:border-border/40"}`}
              >
                <span className="flex flex-col min-w-0">
                  <span className="text-[11px] font-bold truncate">{c.label}</span>
                  <span className="text-[9px] font-mono opacity-40 truncate">{c.name}</span>
                </span>
                {on && <Check className="h-3 w-3 shrink-0 ml-2" />}
              </button>
            );
          })}
          {candidates.length === 0 && (
            <p className="col-span-full text-xs text-muted-foreground py-3">{p.fieldPermsNoFields}</p>
          )}
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-2">
        <Button
          type="button"
          onClick={save}
          disabled={saving || !draft}
          className="flex-1 bg-beige text-cream hover:bg-beige-dark rounded-full text-[11px] font-medium h-10"
        >
          {saving ? <VocifySpinner size={12} /> : null}
          {p.fieldPermsSave.replace("{name}", scopeName)}
        </Button>
        {hasOwnLists && (
          <Button
            type="button"
            variant="outline"
            onClick={resetAll}
            disabled={saving}
            className="rounded-full text-[11px] h-10 border-border/50"
          >
            {p.fieldPermsResetAll.replace("{parent}", parentLabel)}
          </Button>
        )}
      </div>
    </div>
  );
};
