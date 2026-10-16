import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, Mic, Square, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { SettingsSection } from "@/components/ui/settings-card";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { VocifySpinner } from "@/components/ui/vocify-loader";
import { getDesktopBridge, isDesktopHost } from "@/lib/desktop-host";
import {
  ECHO_GUARD_MS,
  REPLY_QUIET_MS,
  addBuyerLine,
  addSellerText,
  base64ToArrayBuffer,
  createDemoSession,
  hasPendingSeller,
  historyBeforeLastSeller,
  takeSellerTurn,
  type DemoSession,
  type DemoTurn,
} from "@/lib/demo-session";
import { useLanguage } from "@/lib/i18n";
import { demoBuyerApi, type DemoClip, type DemoLanguage, type DemoScenario } from "./api";

type UrlKind = "prospect" | "offer";

const SCENARIO_KEY = "vocify_demo_scenario";
const OFFER_KEY = "vocify_demo_offer";

type MicState = "idle" | "waiting" | "listening" | "blocked" | "missing" | "offline";

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  onaudiostart: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
};

function speechRecognition(): (new () => Recognition) | null {
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function savedOffer(): string {
  try {
    return localStorage.getItem(OFFER_KEY) ?? "";
  } catch {
    return "";
  }
}

function loadSaved(): DemoScenario | null {
  try {
    const raw = localStorage.getItem(SCENARIO_KEY);
    return raw ? (JSON.parse(raw) as DemoScenario) : null;
  } catch {
    return null;
  }
}

/** One web address: reading it fills every field the site answers, for the prospect's company or for your own. */
function UrlFill({
  value,
  onChange,
  kind,
  onKind,
  busy,
  copy,
  onRead,
}: {
  value: string;
  onChange: (value: string) => void;
  kind: UrlKind;
  onKind: (kind: UrlKind) => void;
  busy: boolean;
  copy: Record<string, string>;
  onRead: () => void;
}) {
  return (
    <div className="grid gap-2">
      <div className="flex items-center gap-2">
        <Input
          type="url"
          inputMode="url"
          placeholder={copy.demoUrlPlaceholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && value.trim()) {
              e.preventDefault();
              onRead();
            }
          }}
        />
        <Button type="button" variant="outline" size="sm" disabled={busy || !value.trim()} onClick={onRead}>
          {busy ? <VocifySpinner /> : null}
          {copy.demoRead}
        </Button>
      </div>
      <Segmented
        aria-label={copy.demoUrlKind}
        value={kind}
        onValueChange={onKind}
        options={[
          { value: "prospect", label: copy.demoUrlProspect },
          { value: "offer", label: copy.demoUrlOffer },
        ]}
      />
    </div>
  );
}

/**
 * The AI buyer for sales demos (owner/admin, behind DEMO_BUYER_ENABLED). It plays objections out loud so the island
 * hears them as the other side of the call. The desktop app's own audio never reaches the island, so the page runs in
 * a browser; the seller's free speech is picked up by the browser's speech recognition.
 */
export default function DemoBuyerSection() {
  const { t } = useLanguage();
  const copy = t.product;
  const [scenario, setScenario] = useState<DemoScenario | null>(null);
  const [form, setForm] = useState({ offer: savedOffer(), niche: "", company: "", name: "", language: "es" as DemoLanguage });
  const [busy, setBusy] = useState(false);
  const [thinking, setThinking] = useState(false);
  // Off by default: the browser's speech recognition takes the mic, which can leave the desktop recording with silence.
  const [free, setFree] = useState(false);
  const [url, setUrl] = useState("");
  const [urlKind, setUrlKind] = useState<UrlKind>("prospect");
  const [reading, setReading] = useState(false);
  const [context, setContext] = useState("");
  const [mic, setMic] = useState<MicState>("idle");
  const [heard, setHeard] = useState("");
  const [played, setPlayed] = useState<Set<string>>(new Set());
  const [log, setLog] = useState<DemoTurn[]>([]);

  const session = useRef<DemoSession>(createDemoSession());
  const ctx = useRef<AudioContext | null>(null);
  const buffers = useRef(new Map<string, AudioBuffer>());
  const current = useRef<AudioBufferSourceNode | null>(null);
  const playing = useRef(false);
  const playedUntil = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const token = useRef(0);
  const freeRef = useRef(free);
  freeRef.current = free;
  const desktop = isDesktopHost();

  const audio = () => (ctx.current ??= new AudioContext());

  const decode = useCallback(async (id: string, b64: string) => {
    buffers.current.set(id, await audio().decodeAudioData(base64ToArrayBuffer(b64)));
  }, []);

  const stopAudio = useCallback(() => {
    const src = current.current;
    if (src) {
      src.onended = null;
      try {
        src.stop();
      } catch {
        /* already stopped */
      }
      current.current = null;
    }
    if (playing.current) playedUntil.current = Date.now();
    playing.current = false;
  }, []);

  const play = useCallback(
    (id: string) => {
      const buffer = buffers.current.get(id);
      if (!buffer) return;
      stopAudio();
      const ac = audio();
      if (ac.state === "suspended") void ac.resume();
      const src = ac.createBufferSource();
      src.buffer = buffer;
      src.connect(ac.destination);
      src.onended = () => {
        playing.current = false;
        playedUntil.current = Date.now();
        current.current = null;
      };
      playing.current = true;
      current.current = src;
      src.start();
    },
    [stopAudio],
  );

  const flushSeller = useCallback(() => {
    const text = takeSellerTurn(session.current);
    if (text) setLog((l) => [...l, { role: "seller", text }]);
    return text;
  }, []);

  const loadScenario = useCallback(
    async (next: DemoScenario) => {
      buffers.current.clear();
      session.current = createDemoSession();
      await Promise.all([next.opening, ...next.objections].map((c) => decode(c.id, c.audio_b64)));
      setLog([]);
      setPlayed(new Set());
      setScenario(next);
    },
    [decode],
  );

  const replyNow = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    if (!scenario || playing.current) return;
    const seller = flushSeller();
    if (!seller) return;
    const mine = (token.current += 1);
    setThinking(true);
    try {
      const out = await demoBuyerApi.reply(scenario, historyBeforeLastSeller(session.current), seller);
      if (mine !== token.current) return;
      await decode(`reply-${mine}`, out.audio_b64);
      if (mine !== token.current) return;
      addBuyerLine(session.current, out.line);
      setLog((l) => [...l, { role: "buyer", text: out.line }]);
      play(`reply-${mine}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      if (mine === token.current) setThinking(false);
    }
  }, [scenario, flushSeller, decode, play]);

  const onSellerText = useCallback(
    (text: string) => {
      if (playing.current || Date.now() - playedUntil.current < ECHO_GUARD_MS) return;
      addSellerText(session.current, text);
      if (timer.current) clearTimeout(timer.current);
      if (freeRef.current && hasPendingSeller(session.current)) timer.current = setTimeout(() => void replyNow(), REPLY_QUIET_MS);
    },
    [replyNow],
  );

  const playClip = (clip: DemoClip) => {
    token.current += 1;
    setThinking(false);
    if (timer.current) clearTimeout(timer.current);
    flushSeller();
    addBuyerLine(session.current, clip.line);
    setLog((l) => [...l, { role: "buyer", text: clip.line }]);
    play(clip.id);
    setPlayed((p) => new Set(p).add(clip.id));
  };

  const mute = () => {
    token.current += 1;
    setThinking(false);
    if (timer.current) clearTimeout(timer.current);
    stopAudio();
  };

  const readUrl = async () => {
    setReading(true);
    try {
      const out = await demoBuyerApi.analyzeUrl(url.trim());
      if (urlKind === "offer") {
        setForm((f) => ({ ...f, offer: out.offer || f.offer, company: f.company }));
      } else {
        setForm((f) => ({ ...f, niche: out.industry || f.niche, company: out.company || f.company }));
        setContext(out.offer);
      }
      if (!out.offer && !out.industry && !out.company) toast.error(copy.demoUrlEmpty);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setReading(false);
    }
  };

  const prepare = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      localStorage.setItem(OFFER_KEY, form.offer.trim());
    } catch {
      /* the offer is typed again next time */
    }
    try {
      const next = await demoBuyerApi.createScenario({
        offer: form.offer.trim(),
        niche: form.niche.trim(),
        company: form.company.trim() || null,
        prospect_name: form.name.trim() || null,
        context: context.trim() || null,
        language: form.language,
      });
      try {
        localStorage.setItem(SCENARIO_KEY, JSON.stringify(next));
      } catch {
        /* too large to keep: prepared again next time */
      }
      await loadScenario(next);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    mute();
    try {
      localStorage.removeItem(SCENARIO_KEY);
    } catch {
      /* nothing saved */
    }
    setScenario(null);
  };

  useEffect(() => {
    const saved = loadSaved();
    if (saved) void loadScenario(saved).catch(() => setScenario(null));
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [loadScenario]);

  // The seller's free speech: the browser's recognition, restarted while the page is live.
  const Recognition = speechRecognition();
  useEffect(() => {
    if (!scenario || !free || !Recognition) {
      setMic("idle");
      return;
    }
    const rec = new Recognition();
    rec.lang = scenario.language === "en" ? "en-US" : "es-ES";
    rec.continuous = true;
    rec.interimResults = true;
    let active = true;
    setMic("waiting");
    rec.onaudiostart = () => setMic("listening");
    rec.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        setHeard(result[0].transcript.trim());
        if (result.isFinal) onSellerText(result[0].transcript);
      }
    };
    rec.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") setMic("blocked");
      else if (event.error === "audio-capture") setMic("missing");
      else if (event.error === "network") setMic("offline");
    };
    rec.onend = () => {
      if (!active) return;
      setMic((m) => (m === "blocked" || m === "missing" ? m : "waiting"));
      try {
        rec.start();
      } catch {
        /* already starting */
      }
    };
    try {
      rec.start();
    } catch {
      setMic("blocked");
    }
    return () => {
      active = false;
      rec.onend = null;
      rec.stop();
      setMic("idle");
    };
  }, [scenario, free, Recognition, onSellerText]);

  useEffect(() => () => {
    stopAudio();
    void ctx.current?.close();
  }, [stopAudio]);

  if (desktop) {
    return (
      <SettingsSection label={copy.settingsNavDemo}>
        <div className="flex flex-col items-start gap-3 p-4">
          <p className="text-sm text-muted-foreground">{copy.demoDesktopNote}</p>
          <Button variant="outline" onClick={() => void getDesktopBridge()?.shell.openExternal(window.location.href)}>
            <ExternalLink className="h-4 w-4" strokeWidth={1.5} /> {copy.demoOpenBrowser}
          </Button>
        </div>
      </SettingsSection>
    );
  }

  if (!scenario) {
    return (
      <SettingsSection label={copy.demoPrepareLabel}>
        <form onSubmit={prepare} className="flex flex-col gap-3 p-4">
          <UrlFill
            value={url}
            onChange={setUrl}
            kind={urlKind}
            onKind={setUrlKind}
            busy={reading}
            copy={copy as unknown as Record<string, string>}
            onRead={() => void readUrl()}
          />
          <label className="grid gap-1 text-xs text-muted-foreground">
            {copy.demoOffer}
            <Textarea required rows={2} value={form.offer} onChange={(e) => setForm({ ...form, offer: e.target.value })} />
          </label>
          <label className="grid gap-1 text-xs text-muted-foreground">
            {copy.demoNiche}
            <Input required value={form.niche} onChange={(e) => setForm({ ...form, niche: e.target.value })} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="grid gap-1 text-xs text-muted-foreground">
              {copy.demoCompany}
              <Input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
            </label>
            <label className="grid gap-1 text-xs text-muted-foreground">
              {copy.demoName}
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
          </div>
          <div className="flex items-center justify-between gap-3">
            <Segmented
              aria-label={copy.demoLanguage}
              value={form.language}
              onValueChange={(language) => setForm({ ...form, language })}
              options={[
                { value: "es", label: "ES" },
                { value: "en", label: "EN" },
              ]}
            />
            <Button type="submit" disabled={busy}>
              {busy ? <VocifySpinner /> : null}
              {busy ? copy.demoPreparing : copy.demoPrepare}
            </Button>
          </div>
        </form>
      </SettingsSection>
    );
  }

  const clips = [scenario.opening, ...scenario.objections];
  return (
    <div className="flex flex-col gap-6">
      <SettingsSection
        label={`${scenario.persona.name} · ${scenario.persona.role}, ${scenario.persona.company}`}
        action={
          <Button variant="link" size="sm" onClick={reset}>
            {copy.demoNew}
          </Button>
        }
      >
        <p className="p-4 text-sm text-muted-foreground">{scenario.persona.background}</p>
      </SettingsSection>

      <SettingsSection
        label={copy.demoObjections}
        action={
          <Button variant="ghost" size="sm" onClick={mute}>
            <Square className="h-3.5 w-3.5" strokeWidth={1.5} /> {copy.demoMute}
          </Button>
        }
      >
        <div className="grid grid-cols-1 gap-2 p-3 sm:grid-cols-2">
          {clips.map((clip) => (
            <button
              key={clip.id}
              type="button"
              onClick={() => playClip(clip)}
              className={`rounded-xl border border-border/60 px-3 py-2 text-left transition-colors hover:bg-muted/60 ${played.has(clip.id) ? "opacity-60" : ""}`}
            >
              <span className="flex items-center gap-1.5 text-sm font-medium">
                <Volume2 className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.5} /> {clip.id === "opening" ? copy.demoOpening : clip.label}
              </span>
              <span className="mt-0.5 block text-xs text-muted-foreground">{clip.line}</span>
            </button>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection label={copy.demoConversation}>
        <div className="flex items-center justify-between gap-3 border-b border-dashed border-border/60 p-3">
          <span className="flex items-center gap-2 text-sm">
            <Mic className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
            {Recognition ? copy.demoFreeReply : copy.demoNoSpeech}
          </span>
          <div className="flex items-center gap-2">
            {thinking ? <VocifySpinner /> : null}
            <Button variant="ghost" size="sm" onClick={() => void replyNow()} disabled={!scenario}>
              {copy.demoReplyNow}
            </Button>
            <Switch checked={free && Boolean(Recognition)} disabled={!Recognition} onCheckedChange={setFree} aria-label={copy.demoFreeReply} />
          </div>
        </div>
        {free && Recognition ? (
          <div className="flex items-center gap-2 border-b border-dashed border-border/60 px-3 py-2 text-xs text-muted-foreground" role="status">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                mic === "listening" ? "bg-success" : mic === "waiting" ? "bg-warning" : "bg-destructive"
              }`}
            />
            <span className="min-w-0 truncate">
              {mic === "listening"
                ? heard
                  ? `${copy.demoHeard}: ${heard}`
                  : copy.demoMicListening
                : mic === "blocked"
                  ? copy.demoMicBlocked
                  : mic === "missing"
                    ? copy.demoMicMissing
                    : mic === "offline"
                      ? copy.demoMicOffline
                      : copy.demoMicWaiting}
            </span>
          </div>
        ) : null}
        <div className="flex max-h-64 flex-col gap-1.5 overflow-y-auto p-3 text-sm">
          {log.map((turn, i) => (
            <p key={i} className={turn.role === "buyer" ? "text-foreground" : "text-muted-foreground"}>
              <span className="font-medium">{turn.role === "buyer" ? scenario.persona.name : copy.demoYou}:</span> {turn.text}
            </p>
          ))}
        </div>
      </SettingsSection>
    </div>
  );
}
