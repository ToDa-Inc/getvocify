// Hoy card reason labels. The Hoy cards (via product-catalog) and the pre-call brief read them from here.
export const HOY_SIGNAL_COPY = {
  es: { today_signal_pain: "Dolor confirmado", today_signal_uncalled: "Sin llamar" },
  en: { today_signal_pain: "Confirmed pain", today_signal_uncalled: "Not called yet" },
};

/** Priority reason from the API -> Hoy card label key. Mirrors the cards' pain_confirmed / uncalled types. */
export const PRIORITY_REASON_LABEL = {
  pain_agree_next_step: "today_signal_pain",
  no_calls_logged: "today_signal_uncalled",
};
