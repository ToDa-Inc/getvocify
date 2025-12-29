import { X } from "lucide-react";

const painPoints = [
  "Sitting in your car after meetings, frantically typing notes before you forget",
  "End-of-day CRM catch-up when you just want to go home",
  'Incomplete records because you "forgot to log it"',
  '"Why isn\'t your CRM updated?" — Manager',
  "Lost deals because you missed a follow-up you never wrote down",
];

const ProblemSection = () => {
  return (
    <section className="py-20 bg-background grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-bold text-foreground text-center mb-12">
            You're Wasting 5+ Hours Every Week on This:
          </h2>

          <div className="space-y-4 mb-10">
            {painPoints.map((point, index) => (
              <div
                key={index}
                className="flex items-start gap-4 p-4 rounded-xl bg-destructive/5 border border-destructive/10"
              >
                <div className="flex-shrink-0 w-6 h-6 rounded-full bg-destructive/10 flex items-center justify-center">
                  <X className="w-4 h-4 text-destructive" />
                </div>
                <p className="text-foreground">{point}</p>
              </div>
            ))}
          </div>

          <div className="bg-secondary/50 rounded-2xl p-6 border border-border">
            <p className="text-muted-foreground text-center leading-relaxed">
              <span className="font-semibold text-foreground">The result?</span> Your manager thinks you're not working. 
              Your pipeline is a mess. And you're spending selling time doing admin work.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ProblemSection;
