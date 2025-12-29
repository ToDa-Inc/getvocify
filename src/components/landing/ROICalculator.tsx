import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

const ROICalculator = () => {
  const [reps, setReps] = useState(10);
  const [salary, setSalary] = useState(50000);

  const hoursPerWeek = 5;
  const weeksPerYear = 48;
  const totalHours = hoursPerWeek * reps * weeksPerYear;
  const hourlyRate = salary / (weeksPerYear * 40);
  const wastedCost = Math.round(totalHours * hourlyRate);
  const voicfyCost = 25 * reps * 12;
  const savings = wastedCost - voicfyCost;
  const roi = Math.round((savings / voicfyCost) * 100);

  return (
    <section className="py-24 bg-background grain-overlay">
      <div className="container mx-auto px-6 relative z-10">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-foreground mb-4">
              Your Time is Worth More Than CRM Data Entry
            </h2>
            <p className="text-muted-foreground">Tell us about your team</p>
          </div>

          <div className="bg-card rounded-2xl p-8 shadow-medium border border-border">
            <div className="grid md:grid-cols-2 gap-6 mb-8">
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Number of sales reps
                </label>
                <input
                  type="number"
                  value={reps}
                  onChange={(e) => setReps(Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-full px-4 py-3 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-beige/50"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Average salary per rep (€)
                </label>
                <input
                  type="number"
                  value={salary}
                  onChange={(e) => setSalary(Math.max(1000, parseInt(e.target.value) || 1000))}
                  className="w-full px-4 py-3 rounded-xl border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-beige/50"
                />
              </div>
            </div>

            <div className="border-t border-border pt-8 space-y-4">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Time Wasted Per Year:</span>
                <span className="font-medium text-foreground">
                  {hoursPerWeek}h/week × {reps} reps × {weeksPerYear} weeks = {totalHours.toLocaleString()} hours
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Cost of Wasted Time:</span>
                <span className="font-medium text-foreground">
                  €{wastedCost.toLocaleString()}/year
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Voicfy Cost:</span>
                <span className="font-medium text-foreground">
                  €25/month × {reps} reps × 12 = €{voicfyCost.toLocaleString()}/year
                </span>
              </div>
              
              <div className="border-t border-border pt-4 mt-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-lg font-semibold text-foreground">YOUR SAVINGS:</span>
                  <span className="text-2xl font-bold text-green-600">
                    €{savings.toLocaleString()}/year
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-lg font-semibold text-foreground">ROI:</span>
                  <span className="text-2xl font-bold text-beige">
                    {roi.toLocaleString()}%
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-8 text-center">
              <Button variant="hero" size="lg" asChild className="group">
                <Link to="/dashboard">
                  Start Saving Now
                  <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default ROICalculator;
