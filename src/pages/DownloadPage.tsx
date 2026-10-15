import { useEffect } from "react";
import { motion } from "framer-motion";
import { Download } from "lucide-react";
import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";
import { AppleMark, WindowsMark } from "@/components/landing/brand-icons";
import { useLanguage } from "@/lib/i18n";
import { downloadCopy } from "@/lib/landing-download";
import { blurReveal } from "@/lib/scrollReveal";

const userOs = (): "mac" | "windows" | null => {
  const ua = navigator.userAgent;
  if (/Windows/i.test(ua)) return "windows";
  if (/Macintosh|Mac OS X/i.test(ua) && !/Mobile/i.test(ua)) return "mac";
  return null;
};

const DownloadPage = () => {
  const { language } = useLanguage();
  const c = downloadCopy[language];
  const os = userOs();

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  const cards = [
    { id: "windows" as const, Icon: WindowsMark, copy: c.windows, href: "/download/windows" },
    { id: "mac" as const, Icon: AppleMark, copy: c.mac, href: null },
  ];

  return (
    <div className="min-h-screen bg-ink text-cream">
      <Header />
      <main className="px-6 pb-24 pt-40 md:pb-32 md:pt-48">
        <motion.div {...blurReveal(0, 20, 0.98)} className="mx-auto max-w-4xl text-center">
          <h1 className="mb-6 text-balance font-serif text-[clamp(3rem,7vw,5.5rem)] font-normal leading-[0.98] tracking-[-0.02em]">
            {c.title} <span className="chip-glow font-sans text-[0.62em] font-medium tracking-[-0.04em]">{c.accent}</span>
          </h1>
          <p className="mx-auto mb-14 max-w-xl text-lg leading-relaxed text-cream/65">{c.subtitle}</p>

          <div className="mx-auto grid max-w-2xl gap-5 sm:grid-cols-2">
            {cards.map(({ id, Icon, copy, href }) => (
              <div
                key={id}
                className={`flex flex-col items-center rounded-3xl border p-8 ${
                  os === id ? "border-white/25 bg-white/[0.06]" : "border-white/10 bg-white/[0.03]"
                }`}
              >
                <span className="mb-2 h-5 text-xs font-medium text-cream/50">{os === id ? c.forYou : ""}</span>
                <Icon className="mb-4 h-12 w-12" />
                <p className="text-xl font-medium tracking-[-0.03em]">{copy.name}</p>
                <p className="mb-6 mt-1 text-sm text-cream/50">{copy.req}</p>
                {href ? (
                  <a
                    href={href}
                    className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-cream px-6 text-sm font-semibold text-ink transition-all duration-300 ease-silk hover:bg-white active:scale-[0.98]"
                  >
                    <Download className="h-4 w-4" />
                    {copy.cta}
                  </a>
                ) : (
                  <span
                    aria-disabled
                    className="inline-flex h-12 w-full cursor-not-allowed items-center justify-center rounded-2xl border border-white/10 px-6 text-sm font-semibold text-cream/40"
                  >
                    {copy.cta}
                  </span>
                )}
                <p className="mt-4 text-xs leading-snug text-cream/40">{copy.note}</p>
              </div>
            ))}
          </div>

          <p className="mt-12 text-sm text-cream/50">
            {c.help}{" "}
            <a href="mailto:toni@getvocify.com" className="text-cream underline underline-offset-4 hover:text-white">
              toni@getvocify.com
            </a>
          </p>
        </motion.div>
      </main>
      <Footer />
    </div>
  );
};

export default DownloadPage;
