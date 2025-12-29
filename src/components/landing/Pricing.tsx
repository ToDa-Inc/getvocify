import { ArrowRight, Check } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

const plans = [
  {
    name: "SOLO",
    price: "€25",
    period: "/month",
    description: "Perfect for individual reps",
    features: [
      "200 voice memos/month",
      "HubSpot + Pipedrive",
      "Mobile app",
      "Email support",
      "GDPR compliant",
    ],
    cta: "Start Free Trial",
    popular: false,
  },
  {
    name: "TEAM",
    price: "€20",
    period: "/month per user",
    description: "For sales teams (3 users minimum)",
    features: [
      "Unlimited voice memos",
      "All CRM integrations",
      "Team analytics",
      "Shared terminology",
      "Priority support",
      "Manager dashboard",
    ],
    cta: "Start Free Trial",
    popular: true,
  },
  {
    name: "ENTERPRISE",
    price: "Custom",
    period: " pricing",
    description: "For larger organizations",
    features: [
      "Everything in Team",
      "SSO & SAML",
      "Dedicated account manager",
      "Custom integrations",
      "SLA guarantee",
      "Onboarding & training",
    ],
    cta: "Book a Demo",
    popular: false,
  },
];

const Pricing = () => {
  return (
    <section id="pricing" className="py-24 bg-background grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
            Simple Pricing. Massive Time Savings.
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto mb-8">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`relative bg-card rounded-2xl p-6 shadow-soft border ${
                plan.popular ? "border-beige ring-2 ring-beige/20" : "border-border"
              }`}
            >
              {plan.popular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-beige text-cream text-xs font-semibold px-3 py-1 rounded-full">
                  Most Popular
                </span>
              )}
              
              <div className="text-center mb-6">
                <h3 className="text-lg font-bold text-foreground mb-2">{plan.name}</h3>
                <div className="flex items-baseline justify-center gap-1">
                  <span className="text-3xl font-bold text-foreground">{plan.price}</span>
                  <span className="text-sm text-muted-foreground">{plan.period}</span>
                </div>
                <p className="text-sm text-muted-foreground mt-2">{plan.description}</p>
              </div>

              <ul className="space-y-3 mb-6">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm">
                    <Check className="w-4 h-4 text-green-600 flex-shrink-0" />
                    <span className="text-foreground">{feature}</span>
                  </li>
                ))}
              </ul>

              <Button
                variant={plan.popular ? "hero" : "outline"}
                className="w-full group"
                asChild
              >
                <Link to="/dashboard">
                  {plan.cta}
                  <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                </Link>
              </Button>
            </div>
          ))}
        </div>

        <p className="text-center text-sm text-muted-foreground">
          All plans include 14-day free trial. No credit card required.
        </p>
      </div>
    </section>
  );
};

export default Pricing;
