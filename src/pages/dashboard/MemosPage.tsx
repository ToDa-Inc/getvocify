import { Link } from "react-router-dom";
import { Mic } from "lucide-react";

const memos = [
  {
    id: "1",
    company: "Acme Corp",
    preview: "Great meeting with John about the Q1 expansion plans and potential integration with their existing systems...",
    status: "approved",
    time: "2 hours ago",
    duration: "1:23",
  },
  {
    id: "2",
    company: "TechStart Inc",
    preview: "Follow-up call regarding the enterprise license and discussed pricing tiers for their team of 50...",
    status: "pending",
    time: "5 hours ago",
    duration: "2:05",
  },
  {
    id: "3",
    company: "Global Solutions",
    preview: "Initial discovery call with the VP of Engineering. They are looking for a solution to streamline...",
    status: "processing",
    time: "1 day ago",
    duration: "0:58",
  },
  {
    id: "4",
    company: "InnovateCo",
    preview: "Discussed pricing options and implementation timeline. They want to start with a pilot program...",
    status: "approved",
    time: "2 days ago",
    duration: "1:45",
  },
  {
    id: "5",
    company: "NextGen Systems",
    preview: "Product demo went well, they want to move forward with the enterprise plan. Decision maker is...",
    status: "approved",
    time: "3 days ago",
    duration: "2:12",
  },
  {
    id: "6",
    company: "CloudFirst",
    preview: "Quarterly review meeting. They are happy with the results and want to expand to more teams...",
    status: "approved",
    time: "4 days ago",
    duration: "1:30",
  },
];

const getStatusBadge = (status: string) => {
  switch (status) {
    case "approved":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-success/10 text-success">
          <span className="w-1.5 h-1.5 rounded-full bg-success" />
          Approved
        </span>
      );
    case "pending":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-warning/10 text-warning">
          <span className="w-1.5 h-1.5 rounded-full bg-warning" />
          Pending Review
        </span>
      );
    case "processing":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-muted text-muted-foreground">
          <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-pulse" />
          Processing...
        </span>
      );
    default:
      return null;
  }
};

const MemosPage = () => {
  return (
    <div className="max-w-4xl mx-auto animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Voice Memos</h1>
          <p className="text-muted-foreground">All your recorded voice memos</p>
        </div>
      </div>

      {memos.length === 0 ? (
        <div className="bg-card rounded-3xl shadow-medium p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-secondary flex items-center justify-center">
            <Mic className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">No voice memos yet</h3>
          <p className="text-muted-foreground mb-6">Record your first memo to see it here</p>
          <Link 
            to="/dashboard/record"
            className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-xl font-medium hover:bg-primary/80 transition-colors"
          >
            <Mic className="h-4 w-4" />
            Record Memo
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {memos.map((memo) => (
            <Link
              key={memo.id}
              to={`/dashboard/memos/${memo.id}`}
              className="block bg-card rounded-2xl p-5 shadow-soft hover:shadow-medium transition-all hover:-translate-y-0.5"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-4 flex-1 min-w-0">
                  <div className="w-10 h-10 rounded-xl bg-secondary flex items-center justify-center flex-shrink-0">
                    <Mic className="h-5 w-5 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <h3 className="font-semibold text-foreground">{memo.company}</h3>
                      <span className="text-xs text-muted-foreground">{memo.duration}</span>
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {memo.preview}
                    </p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 flex-shrink-0">
                  {getStatusBadge(memo.status)}
                  <span className="text-xs text-muted-foreground">{memo.time}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

export default MemosPage;
