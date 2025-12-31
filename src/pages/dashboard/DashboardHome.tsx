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

import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";

const DashboardHome = () => {
  return (
    <div className={`max-w-5xl mx-auto space-y-8 ${THEME_TOKENS.motion.fadeIn}`}>
      {/* Welcome Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className={V_PATTERNS.dashboardHeader}>
          <h1 className={THEME_TOKENS.typography.pageTitle}>
            Welcome back, <span className={THEME_TOKENS.typography.accentTitle}>John</span>
          </h1>
          <p className={THEME_TOKENS.typography.body}>Ready to update your CRM?</p>
        </div>
        <div className="flex items-center gap-3">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className={`flex items-center gap-2 px-4 py-2 ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.pill}`}
            >
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
              <span className={THEME_TOKENS.typography.capsLabel}>{stat.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Record Card */}
      <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} ${V_PATTERNS.focusBox}`}>
        {/* Animated background glow */}
        <div className="absolute inset-0 bg-gradient-to-tr from-beige/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none" />
        
        <div className="relative z-10">
          <div className={`w-20 h-20 mx-auto mb-8 ${THEME_TOKENS.radius.pill} bg-beige text-cream flex items-center justify-center shadow-large transition-transform duration-500 group-hover:scale-110 group-hover:rotate-3`}>
            <Mic className="h-10 w-10" />
          </div>
          <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-6`}>Record your meeting notes</h2>
          <Button variant="hero" size="xl" asChild className="px-10 rounded-full shadow-large hover:scale-105 active:scale-95 transition-transform">
            <Link to="/dashboard/record">
              <Mic className="h-5 w-5 mr-2" />
              Start Recording
            </Link>
          </Button>
          <p className={`text-sm ${THEME_TOKENS.colors.muted} mt-6 font-medium`}>
            Speak for 30-120 seconds about your meeting
          </p>
        </div>
      </div>

      {/* Recent Memos */}
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className={THEME_TOKENS.typography.sectionTitle}>Recent Memos</h2>
          <Link 
            to="/dashboard/memos" 
            className={`${THEME_TOKENS.typography.capsLabel} text-beige hover:underline`}
          >
            View all
          </Link>
        </div>
        <div className="space-y-4">
          {recentMemos.map((memo) => (
            <Link
              key={memo.id}
              to={`/dashboard/memos/${memo.id}`}
              className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} ${THEME_TOKENS.cards.hover} ${V_PATTERNS.listItem} group`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-foreground text-lg group-hover:text-beige transition-colors">{memo.company}</h3>
                  <p className="text-sm text-muted-foreground truncate mt-1 leading-relaxed">
                    {memo.preview}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-3">
                  {getStatusBadge(memo.status)}
                  <span className={THEME_TOKENS.typography.capsLabel}>{memo.time}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Quick Stats */}
      <div className="space-y-6">
        <h2 className={THEME_TOKENS.typography.sectionTitle}>Quick Stats</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {quickStats.map((stat) => (
            <div
              key={stat.label}
              className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 text-center hover:shadow-medium transition-all`}
            >
              <p className="text-3xl font-black tracking-tighter text-foreground mb-1">{stat.value}</p>
              <p className={THEME_TOKENS.typography.capsLabel}>{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default DashboardHome;
