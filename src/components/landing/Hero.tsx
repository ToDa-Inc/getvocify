import { ArrowRight } from "lucide-react";
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
          <h1 className="text-5xl md:text-7xl lg:text-8xl font-bold leading-[1.1] mb-6">
            <span className="text-muted-foreground">Don't type,</span>
            <br />
            <span className="text-foreground">just speak</span>
          </h1>

          {/* Subheadline */}
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-12">
            The voice-to-CRM AI that turns field notes into perfect HubSpot updates in 60 seconds
          </p>

          {/* Waveform Circle with Rotating Text */}
          <div className="relative w-64 h-64 md:w-80 md:h-80 mx-auto mb-12">
            <RotatingText />
            <WaveformCircle />
          </div>

          {/* CTA */}
          <div className="flex flex-col items-center gap-4">
            <Button variant="hero" size="xl" asChild className="group">
              <Link to="/dashboard">
                Start Free Trial
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            <p className="text-sm text-muted-foreground">
              No credit card required • 14 days free
            </p>
          </div>
        </div>
      </div>

      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-cream via-background to-secondary/30 -z-10" />
    </section>
  );
};

export default Hero;
