import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import Header from "@/components/landing/Header";
import Hero from "@/components/landing/Hero";
import BestRepSection from "@/components/landing/BestRepSection";
import { DemoVideoProvider } from "@/contexts/DemoVideoContext";
import CoachingSection from "@/components/landing/CoachingSection";
import CaptureSection from "@/components/landing/CaptureSection";
import TeamsSection from "@/components/landing/TeamsSection";
import FAQSection from "@/components/landing/FAQSection";
import FinalCTA from "@/components/landing/FinalCTA";
import Footer from "@/components/landing/Footer";

const Index = () => {
  const location = useLocation();

  useEffect(() => {
    const raw = location.hash.replace(/^#/, "");
    if (!raw) return;
    const el = document.getElementById(decodeURIComponent(raw));
    if (el) {
      requestAnimationFrame(() => {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }, [location.pathname, location.hash]);

  return (
    <DemoVideoProvider>
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        <Hero />
        <BestRepSection />
        <CoachingSection />
        <CaptureSection />
        <TeamsSection />
        <FAQSection />
        <FinalCTA />
      </main>
      <Footer />
    </div>
    </DemoVideoProvider>
  );
};

export default Index;
