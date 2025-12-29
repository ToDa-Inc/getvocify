import { ArrowRight, Play } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import WaveformCircle from "./WaveformCircle";
import RotatingText from "./RotatingText";

const Hero = () => {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-16 grain-overlay">
      <div className="container mx-auto px-6 py-20 text-center relative z-10">
        <div className="max-w-4xl mx-auto stagger-children">
          {/* Headline */}
          <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold leading-[1.1] mb-6">
            Stop Typing CRM Notes.
            <br />
            <span className="text-beige">Start Talking.</span>
          </h1>

          {/* Subheadline */}
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-8">
            Voice memos that automatically update your CRM in 60 seconds.
            <br className="hidden md:block" />
            Save 5+ hours per week. Get back to selling.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-8">
            <Button variant="hero" size="xl" asChild className="group">
              <Link to="/dashboard">
                Start Free Trial
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            <Button variant="outline" size="xl" asChild className="group">
              <Link to="#demo">
                <Play className="mr-2 h-4 w-4" />
                Watch 60-Second Demo
              </Link>
            </Button>
          </div>

          {/* Trust Bar */}
          <div className="flex flex-wrap items-center justify-center gap-4 md:gap-6 text-sm text-muted-foreground mb-12">
            <span className="flex items-center gap-1.5">
              <span className="text-green-600">✓</span>
              Works with HubSpot, Salesforce & Pipedrive
            </span>
            <span className="hidden md:inline text-border">|</span>
            <span className="flex items-center gap-1.5">
              <span className="text-green-600">✓</span>
              GDPR Compliant · EU Data Storage
            </span>
            <span className="hidden md:inline text-border">|</span>
            <span className="flex items-center gap-1.5">
              <span className="text-green-600">✓</span>
              No credit card required
            </span>
          </div>

          {/* Waveform Circle with Rotating Text */}
          <div className="relative w-64 h-64 md:w-80 md:h-80 mx-auto">
            <RotatingText />
            <WaveformCircle />
          </div>
        </div>
      </div>

      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-cream via-background to-secondary/30 -z-10" />
    </section>
  );
};

export default Hero;
