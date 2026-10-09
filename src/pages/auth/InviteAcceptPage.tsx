import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { companyApi } from "@/features/company/api";
import { CRM_EMAIL_MATCH_HINT } from "@/lib/identity-hints";
import { useLanguage } from "@/lib/i18n";
import { commercialRoleLabel } from "@/lib/role-labels";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const SALES_ROLE_LABEL_KEYS = {
  sdr: "teamMemberTypeSdr",
  ae: "teamMemberTypeAe",
  general: "teamMemberTypeGeneral",
} as const;

const InviteAcceptPage = () => {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const { applySession } = useAuth();
  const { t } = useLanguage();
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  const { data: preview, isLoading, isError } = useQuery({
    queryKey: ["invite-preview", token],
    queryFn: () => companyApi.previewInvite(token),
    enabled: !!token,
  });

  const acceptMutation = useMutation({
    mutationFn: () => companyApi.acceptInvite(token, password || undefined, fullName || undefined),
    onSuccess: (session) => {
      applySession(session);
      navigate("/dashboard", { replace: true });
    },
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream">
        <VocifyLoader size="md" />
      </div>
    );
  }

  if (isError || !preview) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-cream px-6 text-center">
        <Logo size="md" />
        <p className="mt-6 text-sm text-muted-foreground">This invitation is invalid or has expired.</p>
        <Link to="/login" className="mt-4 text-sm text-beige hover:underline">Go to login</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream px-6">
      <div className={`w-full max-w-md ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 space-y-6`}>
        <div className="text-center">
          <Logo size="sm" className="mx-auto mb-4" />
          <h1 className={THEME_TOKENS.typography.sectionTitle}>Join {preview.companyName ?? "Vocify"}</h1>
          <p className="text-sm text-muted-foreground mt-2">
            {preview.email} ·{" "}
            {preview.role === "owner" || preview.role === "admin"
              ? commercialRoleLabel(preview.role, t.product)
              : `${commercialRoleLabel(preview.role, t.product)} (${t.product[SALES_ROLE_LABEL_KEYS[preview.salesRole ?? "general"]]})`}
          </p>
          <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
            {CRM_EMAIL_MATCH_HINT}
          </p>
        </div>
        <Input placeholder="Your name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        {preview.requiresPassword ? (
          <Input
            type="password"
            placeholder="Create password (min 8 characters)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            You already have a Vocify account. Accepting will add you to this workspace and sign you in.
          </p>
        )}
        {acceptMutation.isError && (
          <p className="text-sm text-destructive">
            {(acceptMutation.error as { data?: { detail?: string } })?.data?.detail
              || "Could not accept invitation"}
          </p>
        )}
        <Button
          className="w-full"
          disabled={(preview.requiresPassword && password.length < 8) || acceptMutation.isPending}
          onClick={() => acceptMutation.mutate()}
        >
          {acceptMutation.isPending ? "Joining…" : "Accept invitation"}
        </Button>
      </div>
    </div>
  );
};

export default InviteAcceptPage;
