import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import Header from "@/components/landing/Header";
import Hero from "@/components/landing/Hero";
import ProblemSection from "@/components/landing/ProblemSection";
import { DemoVideoProvider } from "@/contexts/DemoVideoContext";
import SolutionSection from "@/components/landing/SolutionSection";
import Features from "@/components/landing/Features";
import SocialProof from "@/components/landing/SocialProof";
import ROICalculator from "@/components/landing/ROICalculator";
import ComparisonSection from "@/components/landing/ComparisonSection";
import UseCasesSection from "@/components/landing/UseCasesSection";
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
        <ProblemSection />
        <SolutionSection />
        <Features />
        <SocialProof />
        <ROICalculator />
        <ComparisonSection />
        <UseCasesSection />
        <FAQSection />
        <FinalCTA />
      </main>
      <Footer />
    </div>
    </DemoVideoProvider>
  );
};

export default Index;
