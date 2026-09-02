import { THEME_TOKENS } from "@/lib/theme/tokens";
import { CallerIdSettings } from "@/components/dashboard/settings/CallerIdSettings";
import { DashboardDialer } from "@/components/dashboard/calling/DashboardDialer";
import { useCallingConfig } from "@/features/calls/useCallingConfig";

const CallingPage = () => {
  const { config, isLoading } = useCallingConfig();
  const enabled = Boolean(config?.enabled);

  return (
    <div className={`mx-auto max-w-md space-y-4 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="mb-3 space-y-1">
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          <span className={THEME_TOKENS.typography.accentTitle}>Calling</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>
          Llama con tu número verificado. El prospecto ve ese Caller ID.
        </p>
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} mx-auto max-w-[300px] px-5 py-4`}>
        {isLoading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Cargando…</p>
        ) : enabled ? (
          <DashboardDialer callerIds={config?.callerIds || []} />
        ) : (
          <p className="text-sm text-muted-foreground">
            Twilio no está activo en este entorno. Reinicia el backend con las
            variables TWILIO_* y recarga.
          </p>
        )}
      </div>

      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-6`}>
        <CallerIdSettings />
      </div>
    </div>
  );
};

export default CallingPage;
