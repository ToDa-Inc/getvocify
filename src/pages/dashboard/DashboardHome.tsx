import { Link } from "react-router-dom";
import { Mic, Flame, Clock, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";

const stats = [
  { icon: Flame, label: "6 week streak", color: "text-orange-500" },
  { icon: Mic, label: "127 memos", color: "text-primary" },
  { icon: Clock, label: "8.5 hours saved", color: "text-success" },
];

const recentMemos = [
  {
    id: "1",
    company: "Acme Corp",
    preview: "Great meeting with John about the Q1 expansion plans...",
    status: "approved",
    time: "2 hours ago",
  },
  {
    id: "2",
    company: "TechStart Inc",
    preview: "Follow-up call regarding the enterprise license...",
    status: "pending",
    time: "5 hours ago",
  },
  {
    id: "3",
    company: "Global Solutions",
    preview: "Initial discovery call with the VP of Engineering...",
    status: "processing",
    time: "1 day ago",
  },
  {
    id: "4",
    company: "InnovateCo",
    preview: "Discussed pricing options and implementation timeline...",
    status: "approved",
    time: "2 days ago",
  },
  {
    id: "5",
    company: "NextGen Systems",
    preview: "Product demo went well, they want to move forward...",
    status: "approved",
    time: "3 days ago",
  },
];

const quickStats = [
  { label: "This Week", value: "12 memos" },
  { label: "Time Saved", value: "2.5 hours" },
  { label: "CRM Updates", value: "18 deals" },
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

const DashboardHome = () => {
  return (
    <div className="max-w-5xl mx-auto space-y-8 animate-fade-in">
      {/* Welcome Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Welcome back, John</h1>
          <p className="text-muted-foreground">Ready to update your CRM?</p>
        </div>
        <div className="flex items-center gap-3">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="flex items-center gap-2 px-3 py-2 bg-card rounded-xl shadow-soft"
            >
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
              <span className="text-sm font-medium text-foreground">{stat.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Record Card */}
      <div className="bg-card rounded-3xl shadow-medium p-8 text-center">
        <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-primary flex items-center justify-center">
          <Mic className="h-10 w-10 text-primary-foreground" />
        </div>
        <Button variant="hero" size="xl" asChild>
          <Link to="/dashboard/record">
            <Mic className="h-5 w-5 mr-2" />
            Record Voice Memo
          </Link>
        </Button>
        <p className="text-sm text-muted-foreground mt-4">
          Speak for 30-120 seconds about your meeting
        </p>
        <Link 
          to="/dashboard/record" 
          className="text-sm text-primary hover:underline inline-flex items-center gap-1 mt-2"
        >
          <Upload className="h-4 w-4" />
          Or upload audio file
        </Link>
      </div>

      {/* Recent Memos */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">Recent Memos</h2>
          <Link 
            to="/dashboard/memos" 
            className="text-sm text-primary hover:underline"
          >
            View all
          </Link>
        </div>
        <div className="space-y-3">
          {recentMemos.map((memo) => (
            <Link
              key={memo.id}
              to={`/dashboard/memos/${memo.id}`}
              className="block bg-card rounded-2xl p-4 shadow-soft hover:shadow-medium transition-shadow"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-foreground">{memo.company}</h3>
                  <p className="text-sm text-muted-foreground truncate mt-1">
                    {memo.preview}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                  {getStatusBadge(memo.status)}
                  <span className="text-xs text-muted-foreground">{memo.time}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Quick Stats */}
      <div>
        <h2 className="text-lg font-semibold text-foreground mb-4">Quick Stats</h2>
        <div className="grid grid-cols-3 gap-4">
          {quickStats.map((stat) => (
            <div
              key={stat.label}
              className="bg-card rounded-2xl p-4 shadow-soft text-center"
            >
              <p className="text-2xl font-bold text-foreground">{stat.value}</p>
              <p className="text-sm text-muted-foreground">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default DashboardHome;
