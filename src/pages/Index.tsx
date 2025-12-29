import Header from "@/components/landing/Header";
import Hero from "@/components/landing/Hero";
import ProblemSection from "@/components/landing/ProblemSection";
import SolutionSection from "@/components/landing/SolutionSection";
import Features from "@/components/landing/Features";
import SocialProof from "@/components/landing/SocialProof";
import ROICalculator from "@/components/landing/ROICalculator";
import ComparisonSection from "@/components/landing/ComparisonSection";
import UseCasesSection from "@/components/landing/UseCasesSection";
import FAQSection from "@/components/landing/FAQSection";
import Pricing from "@/components/landing/Pricing";
import FinalCTA from "@/components/landing/FinalCTA";
import Footer from "@/components/landing/Footer";

const Index = () => {
  return (
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
        <Pricing />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  );
};

export default Index;
