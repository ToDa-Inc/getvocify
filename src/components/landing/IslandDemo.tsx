import { useRef, useState } from "react";
import { motion, useMotionValue, useMotionValueEvent, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import {
  ArrowUpRight,
  CalendarDays,
  Check,
  CheckCheck,
  CheckSquare,
  ChevronDown,
  ChevronUp,
  Contact,
  Mail,
  Copy,
  FileText,
  Mic,
  MessageSquare,
  Pause,
  PhoneOff,
  Sparkles,
  User,
  Video,
  X,
} from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { islandCopy, type IslandCopy } from "@/lib/landing-island";
import "./island-demo.css";

/** The demo is driven by scroll, not a timer: each state owns a slice of the sticky section's progress,
 *  and each beat lands at a fraction of its slice. */
const SLICES = [0, 0.2, 0.68, 1];
const BEATS: number[][] = [
  [0, 0.3, 0.6],
  [0.06, 0.17, 0.28, 0.4, 0.52, 0.66, 0.8],
  [0.06, 0.14, 0.22, 0.3, 0.4, 0.58, 0.8],
];
const SIZES = [
  { w: 330, h: 178 },
  { w: 384, h: 408 },
  { w: 376, h: 330 },
];
const START_ELAPSED = 724;
const SCROLL_VH = 300;

const progressToState = (p: number) => {
  const step = p < SLICES[1] ? 0 : p < SLICES[2] ? 1 : 2;
  const local = Math.min(1, Math.max(0, (p - SLICES[step]) / (SLICES[step + 1] - SLICES[step])));
  const tick = BEATS[step].filter((f) => f <= local).length;
  return { step, tick, local };
};

const BRIEF_ICON = { task: CheckSquare, meeting: CalendarDays, chat: MessageSquare } as const;

const clock = (seconds: number) =>
  `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

const Ear = ({ step, elapsed }: { step: number; elapsed: number }) => {
  if (step === 0)
    return (
      <>
        <span className="id-ear">
          <Contact size={14} strokeWidth={1.6} />
        </span>
        <span className="id-ear">
          <ChevronUp size={13} />
        </span>
      </>
    );
  if (step === 1)
    return (
      <>
        <span className="id-ear">
          <span className="id-dot" />
          <span className="id-elapsed">{clock(elapsed)}</span>
        </span>
        <span className="id-ear">
          <span className="id-wave" aria-hidden>
            <span /><span /><span /><span /><span />
          </span>
          <ChevronUp size={13} />
        </span>
      </>
    );
  return (
    <>
      <span className="id-ear id-beige">
        <CheckCheck size={15} strokeWidth={1.8} />
      </span>
      <span className="id-ear">
        <ChevronUp size={13} />
      </span>
    </>
  );
};

const BeforeBody = ({ c, tick }: { c: IslandCopy["before"]; tick: number }) => (
  <>
    <div className="id-contact">
      <span className="id-contact-name">{c.contact}</span>
      <span className="id-pill">
        <i />
        {c.record}
      </span>
      <span className="id-icon">
        <X size={13} />
      </span>
    </div>
    <div className="id-hairline" style={{ margin: "4px 14px 0" }} />
    <div className="id-brief">
      {c.brief.slice(0, tick).map((line) => {
        const Icon = BRIEF_ICON[line.kind];
        return (
          <div key={line.text} className="id-brief-line">
            <Icon size={12} strokeWidth={1.6} />
            <span className="id-brief-text">{line.text}</span>
            <span className="id-brief-when">{line.when}</span>
          </div>
        );
      })}
    </div>
  </>
);

const visibleTurns = (tick: number) => (tick <= 3 ? tick : tick <= 5 ? 3 : tick - 2);

const DuringBody = ({ c, tick }: { c: IslandCopy["during"]; tick: number }) => {
  const visible = visibleTurns(tick);
  return (
    <>
      <div className="id-controls">
        <span className="id-circle">
          <Pause size={12} fill="currentColor" />
        </span>
        <span className="id-stop">
          <i />
          {c.stop}
        </span>
        <span className="id-tag id-grow">
          {c.callType}
          <ChevronDown size={10} />
        </span>
        <span className="id-icon">
          <Copy size={12} />
        </span>
        <Sparkles size={12} className="id-beige" />
        <span className="id-switch" />
        <span className="id-icon">
          <ArrowUpRight size={13} />
        </span>
      </div>
      <div className="id-help" key={tick >= 5 ? "answer" : tick >= 4 ? "drafting" : "empty"}>
        {tick < 4 ? (
          <>
            <span className="id-help-heading">
              <Sparkles size={11} />
              {c.liveHelp}
            </span>
            <span className="id-help-empty">{c.helpEmpty}</span>
          </>
        ) : (
          <>
            <span className="id-help-heading">
              <Sparkles size={11} />
              {c.helpHeading}
            </span>
            <span className="id-help-bridge">{c.helpBridge}</span>
            {tick >= 5 ? (
              <span className="id-help-say">{c.helpSay}</span>
            ) : (
              <span className="id-drafting" aria-hidden>
                <i /><i /><i />
              </span>
            )}
          </>
        )}
      </div>
      <div className="id-hairline" />
      <div className="id-transcript">
        {c.turns.slice(0, visible).map((turn) => (
          <div key={turn.text} className="id-turn" data-you={turn.you}>
            {turn.label && <span className="id-turn-label">{turn.label}</span>}
            <span className="id-bubble" data-you={turn.you}>
              {turn.text}
            </span>
          </div>
        ))}
      </div>
    </>
  );
};

const AfterBody = ({ c, tick, ended }: { c: IslandCopy["after"]; tick: number; ended: string }) => {
  let index = 0;
  const emailTab = tick >= 6;
  return (
    <div className="id-card">
      <div className="id-card-head">
        <span className="id-card-title">
          {c.title}
          <span className="id-card-meta">{ended}</span>
        </span>
        <span className="id-icon">
          <X size={13} />
        </span>
      </div>
      <div className="id-tabs">
        <span className="id-tab" data-active={!emailTab}>
          {c.tabCrm}
          <span className="id-badge">4</span>
        </span>
        <span className="id-tab" data-active={emailTab}>
          <Mail size={11} />
          {c.tabEmail}
        </span>
        <span className="id-tab">
          <FileText size={11} />
          {c.tabNotes}
        </span>
      </div>
      {emailTab ? (
        <div className="id-email" key="email">
          <span className="id-email-to">{c.email.to}</span>
          <span className="id-email-subject">{c.email.subject}</span>
          <span className="id-email-preview">{c.email.preview}</span>
        </div>
      ) : (
        <div key="crm">
          {c.groups.map((group) => (
            <div key={group.label}>
              <div className="id-group">{group.label}</div>
              {group.rows.map((row) => {
                const on = tick > index++;
                return (
                  <div key={row.label} className="id-row">
                    <span className="id-tick" data-on={on}>
                      {on && <Check size={9} strokeWidth={3.5} />}
                    </span>
                    <span className="id-row-label">{row.label}</span>
                    <span className="id-row-value">
                      {row.value}
                      {row.was && <span className="id-was">{row.was}</span>}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
      <div className="id-actions">
        {emailTab ? (
          <span className="id-primary" data-done={tick >= 7}>
            {tick >= 7 && <Check size={12} strokeWidth={2.5} />}
            {tick >= 7 ? c.email.sent : c.email.send}
          </span>
        ) : (
          <span className="id-primary" data-done={tick >= 5}>
            {tick >= 5 && <Check size={12} strokeWidth={2.5} />}
            {tick >= 5 ? c.applied : c.apply}
          </span>
        )}
      </div>
    </div>
  );
};

const IslandDemo = () => {
  const { language } = useLanguage();
  const copy = islandCopy[language];
  const reduced = useReducedMotion() ?? false;
  const track = useRef<HTMLDivElement>(null);
  const [state, setState] = useState(() => progressToState(0));

  const { scrollYProgress } = useScroll({ target: track, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (p) => {
    const next = progressToState(p);
    setState((cur) => (cur.step === next.step && cur.tick === next.tick && Math.floor(cur.local * 40) === Math.floor(next.local * 40) ? cur : next));
  });

  // depth: the scene eases flat as you scroll in, and follows the pointer on top of that
  const px = useSpring(useMotionValue(0), { stiffness: 120, damping: 18 });
  const py = useSpring(useMotionValue(0), { stiffness: 120, damping: 18 });
  const scrollTilt = useTransform(scrollYProgress, [0, 0.12], [reduced ? 0 : 5, 0]);
  const rotateX = useTransform([py, scrollTilt], ([a, b]: number[]) => (reduced ? 0 : a) + b);
  const rotateY = useTransform(px, (v) => (reduced ? 0 : v));

  const { step, tick, local } = state;
  const elapsed = START_ELAPSED + Math.round(local * 38);
  const size = SIZES[step];
  const lastTurn = step === 1 ? copy.during.turns[visibleTurns(tick) - 1] : undefined;
  const lastTurnThem = step === 1 && !!lastTurn && !lastTurn.you;
  const lastTurnYou = step === 1 && !!lastTurn && lastTurn.you;

  const goTo = (i: number) => {
    const el = track.current;
    if (!el) return;
    const range = el.offsetHeight - window.innerHeight;
    const top = el.getBoundingClientRect().top + window.scrollY + range * (SLICES[i] + 0.012);
    window.scrollTo({ top, behavior: reduced ? "auto" : "smooth" });
  };

  return (
    <div ref={track} className="relative" style={{ height: `${SCROLL_VH}vh` }}>
      {["demo-before", "demo-during", "demo-after"].map((id, i) => (
        <span
          key={id}
          id={id}
          aria-hidden
          className="pointer-events-none absolute left-0 h-px w-px"
          style={{ top: `calc((${SCROLL_VH}vh - 100vh) * ${SLICES[i] + 0.012})` }}
        />
      ))}
      <div className="sticky top-24">
        <div
          className="id-stage"
          role="img"
          aria-label={copy.steps[step].title}
          onPointerMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            px.set(((e.clientX - r.left) / r.width - 0.5) * 9);
            py.set(-((e.clientY - r.top) / r.height - 0.5) * 6);
          }}
          onPointerLeave={() => {
            px.set(0);
            py.set(0);
          }}
        >
          <div className="id-scene">
            <motion.div className="id-tilt" style={{ rotateX, rotateY }}>
              {step > 0 && (
                <span className="id-chip" data-pos="right" key={step}>
                  <i />
                  {copy.chips[step === 1 ? "during" : "after"]}
                </span>
              )}

              <div className="id-window" data-phase={["waiting", "live", "ended"][step]} aria-hidden>
                <div className="id-window-bar">
                  <i /><i /><i />
                </div>
                <div className="id-face-wrap">
                  <img src="/demo/caller.jpg" alt="" className="id-face" data-speaking={step === 1 && lastTurnThem} draggable={false} />
                  {step === 1 && (
                    <span className="id-name-chip" data-speaking={lastTurnThem}>
                      <i />
                      Marta Ruiz
                    </span>
                  )}
                  <span className="id-rep" data-speaking={lastTurnYou} data-phase={["waiting", "live", "ended"][step]}>
                    <User size={24} strokeWidth={1.5} />
                    <span className="id-rep-name">
                      <i />
                      {copy.during.repName}
                    </span>
                  </span>
                  {step === 1 && lastTurn && (
                    <div className="id-caption" key={visibleTurns(tick)}>
                      {lastTurn.text}
                    </div>
                  )}
                  {step === 0 && (
                    <div className="id-overlay">
                      <span className="id-pulse" />
                      {copy.stage.before}
                    </div>
                  )}
                  {step === 2 && (
                    <div className="id-overlay" data-ended="true">
                      <PhoneOff size={22} strokeWidth={1.6} />
                      <strong>{copy.stage.after}</strong>
                      <span>
                        {copy.stage.afterMeta} {clock(START_ELAPSED + 38)}
                      </span>
                    </div>
                  )}
                </div>
                <div className="id-window-tools">
                  <span><Mic size={15} /></span>
                  <span><Video size={15} /></span>
                  {step === 0 ? <span data-join="true">{copy.stage.join}</span> : <span data-end="true"><PhoneOff size={15} /></span>}
                </div>
              </div>

              <div className="id-island" style={{ width: size.w, height: size.h }}>
                <div className="id-bg" />
                <div className="id-strip" />
                <div className="id-strip-fade" />
                <div className="id-rim" />
                <div className="id-col">
                  <div className="id-bar">
                    <Ear step={step} elapsed={elapsed} />
                  </div>
                  <div className="id-body" key={step}>
                    {step === 0 && <BeforeBody c={copy.before} tick={tick} />}
                    {step === 1 && <DuringBody c={copy.during} tick={tick} />}
                    {step === 2 && <AfterBody c={copy.after} tick={tick} ended={`${copy.stage.after} · ${clock(START_ELAPSED + 38)}`} />}
                  </div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>

        <div className="id-steps" role="tablist">
          {copy.steps.map((s, i) => (
            <button
              key={s.label}
              type="button"
              role="tab"
              aria-selected={step === i}
              onClick={() => goTo(i)}
              className="id-step"
              data-state={i < step ? "done" : i === step ? "active" : "idle"}
            >
              <span className="id-step-rail">
                <span className="id-step-fill" style={{ width: i < step ? "100%" : i === step ? `${Math.round(local * 100)}%` : "0%" }} />
              </span>
              <span className={`block text-sm font-medium ${step === i ? "text-beige-light" : "text-cream/40"}`}>
                {s.label}
              </span>
              <span className={`mt-1.5 block text-sm font-medium leading-snug tracking-tight md:text-base ${step === i ? "text-cream" : "text-cream/50"}`}>
                {s.title}
              </span>
              <span className="mt-1 hidden text-sm leading-snug text-cream/50 md:block">{s.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default IslandDemo;
