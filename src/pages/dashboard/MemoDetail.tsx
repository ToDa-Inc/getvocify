import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Play, Pause, Check, Edit, X, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

const MemoDetail = () => {
  const { id } = useParams();
  const [isPlaying, setIsPlaying] = useState(false);
  const [approved, setApproved] = useState(false);

  const memoData = {
    company: "Acme Corp",
    transcript: `Had a great meeting with John Smith today about their Q1 expansion plans. They're looking to scale their sales team from 15 to 40 reps over the next quarter. 

The main pain points they mentioned were:
- Current CRM is too slow and clunky
- Sales reps spending 2+ hours daily on data entry
- Difficulty tracking pipeline accurately

They seemed very interested in our voice-to-CRM solution. John mentioned they've tried two other tools but found them lacking. Their budget is around $75,000 for the annual contract.

Next steps:
- Send over a detailed proposal by Friday
- Schedule a demo with their sales leadership team next Tuesday
- Prepare ROI analysis based on their team size

Main competitor mentioned was SalesForce Einstein Voice, but they found it too expensive and complex for their needs.`,
    confidence: 95,
    duration: "1:23",
  };

  const extractedData = {
    company: "Acme Corp",
    dealAmount: "$75,000",
    dealStage: "Proposal",
    closeDate: "2025-03-15",
    contactName: "John Smith",
    contactRole: "VP of Sales",
    contactEmail: "john@acme.com",
    painPoints: [
      "Current CRM is too slow and clunky",
      "Sales reps spending 2+ hours daily on data entry",
      "Difficulty tracking pipeline accurately",
    ],
    nextSteps: [
      "Send over a detailed proposal by Friday",
      "Schedule a demo with their sales leadership team next Tuesday",
      "Prepare ROI analysis based on their team size",
    ],
    competitors: ["SalesForce Einstein Voice"],
  };

  const handleApprove = () => {
    setApproved(true);
    toast.success("HubSpot updated successfully!", {
      description: "Updated deal 'Acme Corp' • Created 2 tasks • Updated contact 'John Smith'",
    });
  };

  if (approved) {
    return (
      <div className="max-w-2xl mx-auto animate-fade-in">
        <div className="bg-card rounded-3xl shadow-medium p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-success/10 flex items-center justify-center">
            <Check className="h-8 w-8 text-success" />
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-2">HubSpot updated successfully!</h2>
          <p className="text-muted-foreground mb-2">
            Updated deal "Acme Corp" • Created 2 tasks • Updated contact "John Smith"
          </p>
          <div className="mt-8">
            <Button variant="hero" size="lg" asChild>
              <Link to="/dashboard/record">Record Another Memo</Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto animate-fade-in">
      {/* Back Link */}
      <Link 
        to="/dashboard/memos" 
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Memos
      </Link>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Left Column - Transcript */}
        <div className="lg:col-span-2 space-y-4">
          {/* Audio Player */}
          <div className="bg-card rounded-2xl shadow-soft p-4">
            <div className="flex items-center gap-4">
              <Button 
                variant="outline" 
                size="icon"
                onClick={() => setIsPlaying(!isPlaying)}
                className="rounded-full"
              >
                {isPlaying ? (
                  <Pause className="h-4 w-4" />
                ) : (
                  <Play className="h-4 w-4 ml-0.5" />
                )}
              </Button>
              <div className="flex-1">
                <div className="h-2 bg-secondary rounded-full">
                  <div className="h-2 bg-primary rounded-full w-1/3" />
                </div>
              </div>
              <span className="text-sm text-muted-foreground">{memoData.duration}</span>
            </div>
          </div>

          {/* Transcript */}
          <div className="bg-card rounded-2xl shadow-soft p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Transcript</h3>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-success/10 text-success">
                <span className="w-1.5 h-1.5 rounded-full bg-success" />
                {memoData.confidence}% accuracy
              </span>
            </div>
            <div className="prose prose-sm text-muted-foreground max-h-[400px] overflow-y-auto">
              {memoData.transcript.split('\n').map((line, i) => (
                <p key={i} className="mb-3">{line}</p>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column - Extracted Data */}
        <div className="lg:col-span-3">
          <div className="bg-card rounded-2xl shadow-soft p-6">
            <h3 className="font-semibold text-foreground mb-6">Extracted CRM Data</h3>
            
            {/* Deal Information */}
            <div className="space-y-6">
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wider">
                  Deal Information
                </h4>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">
                      Company
                      <span className="ml-2 w-2 h-2 rounded-full bg-success inline-block" />
                    </label>
                    <Input defaultValue={extractedData.company} className="bg-input" />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">
                      Deal Amount
                      <span className="ml-2 w-2 h-2 rounded-full bg-success inline-block" />
                    </label>
                    <Input defaultValue={extractedData.dealAmount} className="bg-input" />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">
                      Deal Stage
                      <span className="ml-2 w-2 h-2 rounded-full bg-success inline-block" />
                    </label>
                    <div className="relative">
                      <select className="w-full h-10 px-3 rounded-xl border border-border bg-input text-foreground appearance-none cursor-pointer">
                        <option>Discovery</option>
                        <option selected>Proposal</option>
                        <option>Negotiation</option>
                        <option>Closed Won</option>
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                    </div>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">
                      Close Date
                      <span className="ml-2 w-2 h-2 rounded-full bg-warning inline-block" />
                    </label>
                    <Input type="date" defaultValue={extractedData.closeDate} className="bg-input" />
                  </div>
                </div>
              </div>

              {/* Contact */}
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wider">
                  Contact
                </h4>
                <div className="grid sm:grid-cols-3 gap-4">
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">Name</label>
                    <Input defaultValue={extractedData.contactName} className="bg-input" />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">Role</label>
                    <Input defaultValue={extractedData.contactRole} className="bg-input" />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">Email</label>
                    <Input defaultValue={extractedData.contactEmail} className="bg-input" />
                  </div>
                </div>
              </div>

              {/* Meeting Notes */}
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wider">
                  Meeting Notes
                </h4>
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">Pain Points</label>
                    <Textarea 
                      defaultValue={extractedData.painPoints.map(p => `• ${p}`).join('\n')} 
                      rows={3}
                      className="bg-input"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">Next Steps</label>
                    <Textarea 
                      defaultValue={extractedData.nextSteps.map(s => `• ${s}`).join('\n')} 
                      rows={3}
                      className="bg-input"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-foreground mb-1.5 block">Competitors</label>
                    <div className="flex flex-wrap gap-2">
                      {extractedData.competitors.map((comp) => (
                        <span 
                          key={comp}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary text-sm"
                        >
                          {comp}
                          <button className="hover:text-destructive transition-colors">
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center justify-between gap-4 mt-8 pt-6 border-t border-border">
              <button className="text-sm text-muted-foreground hover:text-destructive transition-colors">
                Reject
              </button>
              <div className="flex items-center gap-3">
                <Button variant="outline">
                  <Edit className="h-4 w-4 mr-2" />
                  Edit & Approve
                </Button>
                <Button variant="hero" onClick={handleApprove}>
                  <Check className="h-4 w-4 mr-2" />
                  Approve & Update CRM
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MemoDetail;
