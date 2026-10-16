import { useCallback, useEffect, useState } from "react";
import { errorCode } from "@/features/playbooks/api";
import { assistantApi, isNotActivated, type GapSession } from "@/features/playbooks/assistantApi";
import type { SourceInput } from "@/features/playbooks/components/PlaybookStart";
import { useLanguage } from "@/lib/i18n";

export type AssistantStatus = "loading" | "ready" | "done" | "error" | "not_activated";

/**
 * The guided questions ("Lo que falta"): the company's open session (or a new one), and the three things done with
 * a question: answer it, leave it for later, take the last answer back. `onChanged` runs whenever the draft changed,
 * so the screens that show the playbook read it again. `problem` is the code of the last failure, for the screen to
 * word; whatever the person wrote stays in their field until an answer is saved.
 */
export function useAssistant({ motionKey, onChanged }: { motionKey: string | null; onChanged: () => void }) {
  const { language } = useLanguage();
  const lang = language === "EN" ? "en" : "es";
  const [session, setSession] = useState<GapSession | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error" | "not_activated">("loading");
  const [saving, setSaving] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [saved, setSaved] = useState<{ gapKey: string; line: string } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadState("loading");
    setProblem(null);
    try {
      setSession(await assistantApi.startGaps({ ...(motionKey ? { motion_key: motionKey } : {}), lang }));
      setLoadState("ready");
    } catch (error) {
      setLoadState(isNotActivated(error) ? "not_activated" : "error");
    }
  }, [motionKey, lang]);

  useEffect(() => {
    void load();
  }, [load]);

  const status: AssistantStatus = loadState !== "ready" ? loadState : session && !session.current ? "done" : "ready";

  /** Saves the answer to the current question. True when it was saved (the field can be emptied). */
  const answer = async (source: SourceInput): Promise<boolean> => {
    const current = session?.current;
    if (!session || !current) return false;
    setSaving(true);
    setProblem(null);
    try {
      const result = await assistantApi.answerGap(session.id, current.key, source);
      setSaved({ gapKey: current.key, line: result.saved_line });
      setSession(result.session);
      onChanged();
      return true;
    } catch (error) {
      setProblem(errorCode(error) ?? "unknown");
      return false;
    } finally {
      setSaving(false);
    }
  };

  const skip = async () => {
    const current = session?.current;
    if (!session || !current) return;
    setProblem(null);
    try {
      setSession(await assistantApi.skipGap(session.id, current.key));
      setSaved(null);
    } catch (error) {
      setProblem(errorCode(error) ?? "unknown");
    }
  };

  /** Takes the last saved answer back and brings its question back. */
  const undo = async () => {
    if (!session || !saved) return;
    setUndoing(true);
    setProblem(null);
    try {
      setSession(await assistantApi.undoGap(session.id, saved.gapKey));
      setSaved(null);
      onChanged();
    } catch (error) {
      setProblem(errorCode(error) ?? "unknown");
    } finally {
      setUndoing(false);
    }
  };

  return { status, session, saved, saving, undoing, problem, answer, skip, undo, reload: load };
}

export type Assistant = ReturnType<typeof useAssistant>;
