import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { SalesStrategySettings } from "@/components/dashboard/settings/SalesStrategySettings";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { authKeys } from "@/features/auth/api";
import { companyApi, companyKeys } from "@/features/company/api";
import type { OnboardingStep } from "@/features/company/types";
import { useLanguage } from "@/lib/i18n";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import TeamPage from "./TeamPage";

/**
 * T9: Head of Sales onboarding wizard (ONBOARDING_WIZARD_ENABLED). Each step reuses an
 * existing page/component rather than duplicating its logic - Team for both invites (D1)
 * and SDR->AE routing (D2), SalesStrategySettings for D10. Every step can be skipped;
 * finishing (or skipping through all five) posts /company/onboarding/complete.
 */
const STEPS: OnboardingStep[] = ["crm", "team", "handoff", "playbooks", "strategy"];

const OnboardingWizard = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [stepIndex, setStepIndex] = useState(0);
  const [initialized, setInitialized] = useState(false);

  const { data: onboarding, isLoading } = useQuery({
    queryKey: [...companyKeys.all, "onboarding"],
    queryFn: () => companyApi.getOnboardingState(),
  });

  // Land on the first step that still looks unfinished, computed once from the server.
  useEffect(() => {
    if (initialized || !onboarding) return;
    const idx = onboarding.nextStep ? STEPS.indexOf(onboarding.nextStep) : 0;
    setStepIndex(idx >= 0 ? idx : 0);
    setInitialized(true);
  }, [onboarding, initialized]);

  const finishMutation = useMutation({
    mutationFn: () => companyApi.completeOnboarding(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: companyKeys.all });
      queryClient.invalidateQueries({ queryKey: authKeys.me() });
      toast.success(t.product.onboardingSavedToast);
      navigate("/dashboard", { replace: true });
    },
    onError: () => toast.error(t.product.onboardingSaveFailedToast),
  });

  if (isLoading || !initialized) {
    return (
      <div className={THEME_TOKENS.interaction.pageLoad}>
        <VocifyLoader size="lg" />
      </div>
    );
  }

  const step = STEPS[stepIndex];
  const isLast = stepIndex === STEPS.length - 1;
  const advance = () => (isLast ? finishMutation.mutate() : setStepIndex((i) => i + 1));

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className={THEME_TOKENS.typography.sectionTitle}>{t.product.onboardingTitle}</h1>
        <p className="text-xs text-muted-foreground mt-1">{t.product.onboardingSubtitle}</p>
        <p className={`${THEME_TOKENS.typography.capsLabel} mt-3`}>
          {t.product.onboardingStepOf
            .replace("{current}", String(stepIndex + 1))
            .replace("{total}", String(STEPS.length))}
        </p>
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6 md:p-8 space-y-6`}>
        {step === "crm" && (
          <div className="space-y-3">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.onboardingStepCrmTitle}</h2>
            <p className="text-sm text-muted-foreground">{t.product.onboardingStepCrmBody}</p>
            <Button
              type="button"
              variant="outline"
              className="rounded-full"
              onClick={() => navigate("/dashboard/settings")}
            >
              {t.product.onboardingStepCrmCta}
            </Button>
          </div>
        )}

        {(step === "team" || step === "handoff") && (
          <div className="space-y-4">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>
              {step === "team" ? t.product.onboardingStepTeamTitle : t.product.onboardingStepHandoffTitle}
            </h2>
            <p className="text-sm text-muted-foreground">
              {step === "team" ? t.product.onboardingStepTeamBody : t.product.onboardingStepHandoffBody}
            </p>
            <TeamPage />
          </div>
        )}

        {step === "playbooks" && (
          <div className="space-y-3">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.onboardingStepPlaybooksTitle}</h2>
            <p className="text-sm text-muted-foreground">{t.product.onboardingStepPlaybooksBody}</p>
            <Button
              type="button"
              variant="outline"
              className="rounded-full"
              onClick={() => navigate("/dashboard/settings/playbooks")}
            >
              {t.product.onboardingStepPlaybooksCta}
            </Button>
          </div>
        )}

        {step === "strategy" && (
          <div className="space-y-2">
            <h2 className={THEME_TOKENS.typography.sectionTitle}>{t.product.onboardingStepStrategyTitle}</h2>
            <p className="text-sm text-muted-foreground">{t.product.onboardingStepStrategyBody}</p>
            <SalesStrategySettings />
          </div>
        )}
      </div>

      <div className="flex items-center justify-between">
        <Button
          type="button"
          variant="ghost"
          disabled={stepIndex === 0}
          onClick={() => setStepIndex((i) => Math.max(i - 1, 0))}
          className="rounded-full"
        >
          {t.product.onboardingBack}
        </Button>
        <div className="flex items-center gap-2">
          {!isLast && (
            <Button type="button" variant="ghost" onClick={advance} className="rounded-full">
              {t.product.onboardingSkip}
            </Button>
          )}
          <Button
            type="button"
            onClick={advance}
            disabled={finishMutation.isPending}
            className="rounded-full bg-beige text-cream px-6"
          >
            {isLast ? t.product.onboardingFinish : t.product.onboardingNext}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingWizard;
