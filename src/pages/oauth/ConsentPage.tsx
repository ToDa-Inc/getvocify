import { useState } from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VocifyLoader, VocifySpinner } from "@/components/ui/vocify-loader";
import { useAuth } from "@/features/auth";
import { ApiError } from "@/shared/lib/api-client";
import { mcpApi } from "@/lib/api/mcp";
import { sessionGateView } from "@/lib/auth-session";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";

function hostOf(uri?: string | null): string | null {
  if (!uri) return null;
  try {
    return new URL(uri).host;
  } catch {
    return null;
  }
}

/**
 * Vocify's OAuth server (api: /oauth/authorize) sends the browser here when an AI app (Claude, ChatGPT…) asks
 * for access to the user's Vocify account. Allow or deny, then back to the app.
 */
const ConsentPage = () => {
  const { t } = useLanguage();
  const location = useLocation();
  const [params] = useSearchParams();
  const authorizationId = params.get("authorization_id") ?? "";
  const { isAuthenticated, isLoading, hasStoredSession } = useAuth();
  const gate = sessionGateView({ isLoading, hasStoredSession, isAuthenticated });
  const [sending, setSending] = useState<"approve" | "deny" | null>(null);
  const [failed, setFailed] = useState<"invalid" | "off" | null>(null);

  const details = useQuery({
    queryKey: ["oauth-authorization", authorizationId],
    queryFn: () => mcpApi.authorization(authorizationId),
    enabled: gate === "ok" && Boolean(authorizationId),
    retry: false,
    staleTime: 0,
  });

  if (gate === "login") {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  }

  const answer = async (action: "approve" | "deny") => {
    setSending(action);
    try {
      const { redirect_url } = await mcpApi.consent(authorizationId, action);
      window.location.assign(redirect_url);
    } catch (error) {
      // 409: the workspace has AI agents off. Anything else: the request expired or was never ours.
      setFailed(error instanceof ApiError && error.status === 409 ? "off" : "invalid");
      setSending(null);
    }
  };

  const invalid = !authorizationId || details.isError || failed === "invalid";
  const request = details.data ?? null;
  const appName = request?.client.client_name || t.product.consentUnknownApp;
  const returnHost = hostOf(request?.redirect_uri);

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-cream">
      <div className={`w-full max-w-md ${THEME_TOKENS.motion.fadeIn}`}>
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-beige/10">
            <Mic className="h-8 w-8 text-beige" strokeWidth={1.5} />
          </div>
        </div>
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8`}>
          {invalid ? (
            <p className="text-sm text-muted-foreground text-center">{t.product.consentInvalid}</p>
          ) : failed === "off" ? (
            <p className="text-sm text-muted-foreground text-center">{t.product.consentOff}</p>
          ) : gate !== "ok" || details.isLoading || !request ? (
            <div className="flex justify-center py-6">
              <VocifyLoader size="sm" />
            </div>
          ) : (
            <div className="space-y-6">
              <div className="space-y-2">
                <h1 className={THEME_TOKENS.typography.sectionTitle}>
                  {appName} {t.product.consentTitle}
                </h1>
                <p className="text-sm text-muted-foreground">{t.product.consentBody}</p>
                {returnHost && (
                  <p className="text-xs text-muted-foreground">
                    {t.product.consentReturnTo} <span className="font-medium text-foreground">{returnHost}</span>
                  </p>
                )}
                {!request.known && (
                  <p className="text-xs text-warning" role="status">{t.product.consentUnrecognised}</p>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" className="rounded-full" disabled={sending !== null} onClick={() => void answer("deny")}>
                  {sending === "deny" ? <VocifySpinner size={14} /> : t.product.consentDeny}
                </Button>
                <Button type="button" className="rounded-full" disabled={sending !== null} onClick={() => void answer("approve")}>
                  {sending === "approve" ? <VocifySpinner size={14} tone="onFill" /> : t.product.consentAllow}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ConsentPage;
