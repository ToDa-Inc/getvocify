import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

const Pricing = () => {
  return (
    <section id="pricing" className="py-24 bg-secondary/30 grain-overlay">
      <div className="container mx-auto px-6 text-center relative z-10">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-6">
            Simple, Transparent Pricing
          </h2>
          
          <p className="text-xl md:text-2xl text-foreground mb-2">
            Just <span className="font-bold">$25/month</span>
          </p>
          
          <p className="text-muted-foreground mb-10">
            Unlimited voice memos • All CRM integrations
          </p>

          <Button variant="hero" size="lg" asChild className="group">
            <Link to="/dashboard">
              See Pricing
              <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
          </Button>
        </div>
      </div>
    </section>
  );
};

export default Pricing;
