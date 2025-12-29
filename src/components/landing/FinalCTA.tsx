import { ArrowRight, Play, Mail } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

const steps = [
  "Start your 14-day free trial (no credit card)",
  "Connect your CRM in 2 minutes",
  "Record your first voice memo",
  "Watch it update automatically",
  "Save 5+ hours this week",
];

const FinalCTA = () => {
  return (
    <section className="py-24 bg-beige grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-cream mb-4">
            Stop Wasting Time on CRM. Start Selling More.
          </h2>
          <p className="text-cream/80 text-lg mb-10">
            Join 500+ sales professionals who've reclaimed their time.
          </p>

          <div className="bg-cream/10 backdrop-blur-sm rounded-2xl p-8 mb-10">
            <p className="text-cream font-medium mb-4">What happens next:</p>
            <ol className="space-y-3 text-left max-w-md mx-auto">
              {steps.map((step, index) => (
                <li key={index} className="flex items-start gap-3 text-cream/90">
                  <span className="flex-shrink-0 w-6 h-6 rounded-full bg-cream/20 flex items-center justify-center text-sm font-semibold">
                    {index + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </div>

          <p className="text-cream/80 mb-8">
            Try Voicfy free for 14 days. If you don't love it, walk away. No charge.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-10">
            <Button 
              size="xl" 
              asChild 
              className="group bg-cream text-beige hover:bg-cream/90"
            >
              <Link to="/dashboard">
                Start Free Trial
                <ArrowRight className="ml-2 h-5 w-5 transition-transform group-hover:translate-x-1" />
              </Link>
            </Button>
            <Button 
              variant="outline" 
              size="xl" 
              asChild 
              className="group border-cream/30 text-cream hover:bg-cream/10"
            >
              <Link to="#demo">
                <Play className="mr-2 h-4 w-4" />
                Watch Demo
              </Link>
            </Button>
          </div>

          <div className="flex items-center justify-center gap-2 text-cream/70 text-sm">
            <Mail className="w-4 h-4" />
            <span>Questions? Email founders@voicfy.com</span>
          </div>
          <p className="text-cream/50 text-xs mt-2">
            We respond in &lt;2 hours during business hours.
          </p>
        </div>
      </div>
    </section>
  );
};

export default FinalCTA;
