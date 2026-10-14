import { motion } from "framer-motion";
import { Check } from "lucide-react";
import type { ReactNode } from "react";
import type { RoleMock } from "@/lib/landing-roles";
import { WhatsAppMark } from "./brand-icons";
import CrmStack from "./CrmStack";

export const MockLabel = ({ children }: { children: ReactNode }) => (
  <p className="mb-2 text-xs font-medium text-muted-foreground">{children}</p>
);

export const SampleBadge = ({ children }: { children: ReactNode }) => (
  <span className="text-xs text-muted-foreground/70">{children}</span>
);

const CheckDot = ({ done }: { done: boolean }) => (
  <span
    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
      done ? "bg-success/15 text-success" : "border border-border text-transparent"
    }`}
  >
    <Check className="h-3 w-3" strokeWidth={3} />
  </span>
);

type Kind<K extends RoleMock["kind"]> = Extract<RoleMock, { kind: K }>;

const PrepCard = ({ mock, sample }: { mock: Kind<"prep">; sample: string }) => (
  <div className="glass-card-strong space-y-5 rounded-2xl p-5 text-left md:p-6">
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-base font-semibold tracking-tight text-foreground">{mock.title}</p>
        <p className="text-xs text-muted-foreground">{mock.meta}</p>
      </div>
      <SampleBadge>{sample}</SampleBadge>
    </div>
    {mock.blocks.map((block) => (
      <div key={block.label}>
        <MockLabel>{block.label}</MockLabel>
        {block.text && <p className="text-sm leading-relaxed text-foreground/80">{block.text}</p>}
        {block.items && (
          <ul className="space-y-2">
            {block.items.map((item) => (
              <li key={item} className="flex items-start gap-2.5 text-sm font-medium text-foreground">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-beige" />
                {item}
              </li>
            ))}
          </ul>
        )}
      </div>
    ))}
  </div>
);

const LiveCard = ({ mock, sample }: { mock: Kind<"live">; sample: string }) => (
  <div className="space-y-3 text-left">
    <div className="flex justify-end">
      <SampleBadge>{sample}</SampleBadge>
    </div>
    <div className="max-w-[88%] rounded-2xl rounded-tl-sm border border-white/70 bg-white/80 px-4 py-3 text-sm text-foreground shadow-soft">
      “{mock.said}”
    </div>
    <div className="ml-auto max-w-[96%] rounded-2xl bg-ink p-4 text-cream shadow-float md:p-5">
      <span className="inline-block rounded-full bg-cream/10 px-2.5 py-1 text-xs font-medium text-cream/80">
        {mock.tag}
      </span>
      <p className="mt-3 text-xs text-cream/50">{mock.answerTitle}</p>
      <p className="mt-1.5 text-sm leading-relaxed text-cream/90">{mock.answer}</p>
    </div>
  </div>
);

const PlaybookCard = ({ mock, sample }: { mock: Kind<"playbook">; sample: string }) => (
  <div className="glass-card-strong rounded-2xl p-5 text-left md:p-6">
    <div className="mb-4 flex items-start justify-between gap-4">
      <p className="text-xs font-medium text-muted-foreground">{mock.title}</p>
      <SampleBadge>{sample}</SampleBadge>
    </div>
    <ul className="space-y-3">
      {mock.items.map((item) => (
        <li key={item.label} className="flex items-center gap-3 text-sm font-medium text-foreground">
          <CheckDot done={item.done} />
          <span className={item.done ? undefined : "text-muted-foreground"}>{item.label}</span>
        </li>
      ))}
    </ul>
    <p className="mt-5 rounded-xl bg-beige/10 p-3.5 text-sm text-foreground/80">{mock.note}</p>
  </div>
);

const DoneCard = ({ mock }: { mock: Kind<"done"> }) => (
  <div className="glass-card-strong rounded-2xl p-5 text-left md:p-6">
    <MockLabel>{mock.title}</MockLabel>
    <ul className="grid gap-2.5 sm:grid-cols-2">
      {mock.items.map((item, i) => (
        <motion.li
          key={item}
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
          className="flex items-center gap-3 rounded-xl border border-border/60 bg-white/70 px-4 py-3 text-sm font-medium text-foreground"
        >
          <CheckDot done />
          {item}
        </motion.li>
      ))}
    </ul>
  </div>
);

const MetricsCard = ({ mock, sample }: { mock: Kind<"metrics">; sample: string }) => (
  <div className="glass-card-strong rounded-2xl p-5 text-left md:p-6">
    <div className="mb-5 flex items-start justify-between gap-4">
      <p className="text-xs font-medium text-muted-foreground">{mock.title}</p>
      <SampleBadge>{sample}</SampleBadge>
    </div>
    <ul className="space-y-4">
      {mock.rows.map((row, i) => (
        <li key={row.label} className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-3 text-sm">
          <span className="truncate font-medium text-foreground">{row.label}</span>
          <span className="h-2 overflow-hidden rounded-full bg-beige/10">
            <motion.span
              initial={{ width: 0 }}
              whileInView={{ width: `${row.value}%` }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 1, delay: 0.15 + i * 0.1, ease: [0.16, 1, 0.3, 1] }}
              className={`block h-full rounded-full ${row.value >= 70 ? "bg-beige" : "bg-beige-light"}`}
            />
          </span>
          <span className="text-right text-xs text-muted-foreground">{row.value}%</span>
        </li>
      ))}
    </ul>
  </div>
);

const WhatsAppCard = ({ mock, sample }: { mock: Kind<"whatsapp">; sample: string }) => (
  <div className="overflow-hidden rounded-2xl border border-border/60 bg-[#efeae2] text-left shadow-soft">
    <div className="flex items-center gap-3 bg-[#075e54] px-4 py-3 text-white">
      <WhatsAppMark className="h-6 w-6" />
      <p className="flex-1 text-sm font-medium">{mock.title}</p>
      <span className="text-xs text-white/60">{sample}</span>
    </div>
    <div className="space-y-2.5 p-4">
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="ml-auto max-w-[85%] rounded-xl rounded-tr-sm bg-[#d9fdd3] px-3.5 py-2.5 text-sm leading-relaxed text-[#111b21] shadow-soft"
      >
        {mock.sent}
      </motion.p>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.5, delay: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="max-w-[85%] rounded-xl rounded-tl-sm bg-white px-3.5 py-2.5 text-sm leading-relaxed text-[#111b21] shadow-soft"
      >
        {mock.reply}
      </motion.p>
    </div>
  </div>
);

const StackCard = ({ mock }: { mock: Kind<"stack"> }) => (
  <div className="glass-card-strong rounded-2xl p-5 text-center md:p-6">
    <MockLabel>{mock.title}</MockLabel>
    <div className="py-6">
      <CrmStack more={mock.more} tone="light" />
    </div>
  </div>
);

const FieldsCard = ({ mock, sample }: { mock: Kind<"fields">; sample: string }) => (
  <div className="glass-card-strong rounded-2xl p-5 text-left md:p-6">
    <div className="mb-4 flex items-start justify-between gap-4">
      <p className="text-sm font-medium text-foreground">{mock.title}</p>
      <SampleBadge>{sample}</SampleBadge>
    </div>
    <ul className="divide-y divide-border/60">
      {mock.rows.map((row, i) => (
        <motion.li
          key={row.label}
          initial={{ opacity: 0, x: -8 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5, delay: i * 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="grid grid-cols-[6.5rem_1fr] items-baseline gap-3 py-3 text-sm"
        >
          <span className="text-muted-foreground">{row.label}</span>
          <span className="font-medium text-foreground">
            {row.from && <span className="mr-2 font-normal text-muted-foreground/70 line-through">{row.from}</span>}
            {row.to}
          </span>
        </motion.li>
      ))}
    </ul>
  </div>
);

const TimelineCard = ({ mock, sample }: { mock: Kind<"timeline">; sample: string }) => {
  const widths = [14, 38, 28, 20];
  return (
    <div className="glass-card-strong rounded-2xl p-5 text-left md:p-6">
      <div className="mb-5 flex items-start justify-between gap-4">
        <p className="text-sm font-medium text-foreground">{mock.title}</p>
        <SampleBadge>{sample}</SampleBadge>
      </div>
      <div className="flex gap-1.5">
        {mock.phases.map((phase, i) => (
          <div key={phase} style={{ width: `${widths[i] ?? 25}%` }} className="min-w-0">
            <div className={`h-2 rounded-full ${i === mock.marked ? "bg-warning" : "bg-beige/15"}`} />
            <p className={`mt-2 truncate text-xs ${i === mock.marked ? "font-medium text-foreground" : "text-muted-foreground/70"}`}>{phase}</p>
          </div>
        ))}
      </div>
      <div className="mt-5 rounded-xl bg-beige/10 p-3.5">
        <p className="text-sm font-medium text-foreground">{mock.moment}</p>
        <p className="mt-1 text-sm text-muted-foreground">{mock.fix}</p>
      </div>
    </div>
  );
};

const FeedbackCard = ({ mock, sample }: { mock: Kind<"feedback">; sample: string }) => (
  <div className="glass-card-strong rounded-2xl p-5 text-left md:p-6">
    <div className="mb-5 flex items-start justify-between gap-4">
      <p className="text-sm font-medium text-foreground">{mock.title}</p>
      <SampleBadge>{sample}</SampleBadge>
    </div>
    <p className="mb-5 text-5xl font-medium tracking-[-0.05em] text-foreground">
      {mock.score}
      <span className="text-2xl text-muted-foreground">%</span>
    </p>
    <div className="space-y-4">
      <div>
        <MockLabel>{mock.goodTitle}</MockLabel>
        <p className="flex items-start gap-2 text-sm font-medium text-foreground">
          <CheckDot done />
          {mock.good}
        </p>
      </div>
      <div className="rounded-xl bg-beige/10 p-3.5">
        <MockLabel>{mock.nextTitle}</MockLabel>
        <p className="text-sm font-medium text-foreground">{mock.next}</p>
        <p className="mt-1 text-sm italic text-muted-foreground">{mock.tryIt}</p>
      </div>
    </div>
  </div>
);

export const RoleMockView = ({ mock, sample }: { mock: RoleMock; sample: string }) => {
  switch (mock.kind) {
    case "prep":
      return <PrepCard mock={mock} sample={sample} />;
    case "live":
      return <LiveCard mock={mock} sample={sample} />;
    case "playbook":
      return <PlaybookCard mock={mock} sample={sample} />;
    case "done":
      return <DoneCard mock={mock} />;
    case "metrics":
      return <MetricsCard mock={mock} sample={sample} />;
    case "whatsapp":
      return <WhatsAppCard mock={mock} sample={sample} />;
    case "stack":
      return <StackCard mock={mock} />;
    case "fields":
      return <FieldsCard mock={mock} sample={sample} />;
    case "timeline":
      return <TimelineCard mock={mock} sample={sample} />;
    case "feedback":
      return <FeedbackCard mock={mock} sample={sample} />;
  }
};
