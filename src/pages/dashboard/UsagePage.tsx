import { BarChart3, Mic, Clock, TrendingUp } from "lucide-react";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { motion } from "framer-motion";

const UsagePage = () => {
  const stats = [
    {
      icon: Mic,
      label: "Total Memos",
      value: "127",
      change: "+12 this week",
      color: "text-beige",
    },
    {
      icon: Clock,
      label: "Time Saved",
      value: "42.5 hrs",
      change: "+2.5 hrs this week",
      color: "text-success",
    },
    {
      icon: BarChart3,
      label: "CRM Updates",
      value: "318",
      change: "+24 this week",
      color: "text-warning",
    },
    {
      icon: TrendingUp,
      label: "Accuracy Rate",
      value: "94.2%",
      change: "+1.2% vs last month",
      color: "text-beige",
    },
  ];

  const weeklyData = [
    { day: "Mon", memos: 4 },
    { day: "Tue", memos: 6 },
    { day: "Wed", memos: 3 },
    { day: "Thu", memos: 8 },
    { day: "Fri", memos: 5 },
    { day: "Sat", memos: 1 },
    { day: "Sun", memos: 0 },
  ];

  const maxMemos = Math.max(...weeklyData.map(d => d.memos));

  return (
    <div className={`max-w-5xl mx-auto space-y-10 ${THEME_TOKENS.motion.fadeIn}`}>
      <div className={V_PATTERNS.dashboardHeader}>
        <h1 className={THEME_TOKENS.typography.pageTitle}>
          Usage <span className={THEME_TOKENS.typography.accentTitle}>Analytics</span>
        </h1>
        <p className={THEME_TOKENS.typography.body}>Track your performance and time saved with Vocify.</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map((stat) => (
          <div key={stat.label} className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 ${THEME_TOKENS.cards.hover}`}>
            <div className={`w-12 h-12 rounded-2xl bg-secondary/5 flex items-center justify-center mb-6`}>
              <stat.icon className={`h-6 w-6 ${stat.color}`} />
            </div>
            <p className="text-3xl font-black tracking-tighter text-foreground mb-1">{stat.value}</p>
            <p className={`${THEME_TOKENS.typography.capsLabel} mb-2`}>{stat.label}</p>
            <p className="text-[10px] font-bold text-success bg-success/5 px-2 py-1 rounded-full w-fit">{stat.change}</p>
          </div>
        ))}
      </div>

      {/* Weekly Chart */}
      <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.container} p-10 relative overflow-hidden group`}>
        <div className="absolute inset-0 bg-gradient-to-br from-beige/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-10`}>Weekly Activity</h2>
        
        <div className="flex items-end justify-between gap-4 h-64 relative z-10">
          {weeklyData.map((day) => (
            <div key={day.day} className="flex-1 flex flex-col items-center gap-4 group/bar relative">
              <div className="w-full flex items-end justify-center h-48">
                <div 
                  className="w-full max-w-[48px] bg-foreground/5 rounded-t-2xl transition-all hover:bg-beige/40 relative"
                  style={{ 
                    height: day.memos > 0 ? `${(day.memos / maxMemos) * 100}%` : '8px',
                  }}
                >
                  {day.memos > 0 && (
                    <div 
                      className="absolute inset-0 bg-beige rounded-t-2xl shadow-[0_0_20px_rgba(245,215,176,0.3)]"
                    />
                  )}
                  <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-white text-foreground text-[10px] font-black px-2 py-1 rounded-lg opacity-0 group-hover/bar:opacity-100 transition-opacity shadow-soft">
                    {day.memos}
                  </div>
                </div>
              </div>
              <div className="text-center">
                <p className={THEME_TOKENS.typography.capsLabel}>{day.day}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Activity */}
      <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-10`}>
        <h2 className={`${THEME_TOKENS.typography.sectionTitle} mb-8`}>Recent Activity Stream</h2>
        
        <div className="space-y-2">
          {[
            { action: "Created memo", company: "Acme Corp", time: "2 hours ago", type: "memo" },
            { action: "Updated deal", company: "TechStart Inc", time: "5 hours ago", type: "sync" },
            { action: "Created contact", company: "Global Solutions", time: "1 day ago", type: "sync" },
            { action: "Created memo", company: "InnovateCo", time: "2 days ago", type: "memo" },
            { action: "Updated deal", company: "NextGen Systems", time: "3 days ago", type: "sync" },
          ].map((activity, i) => (
            <div key={i} className={`flex items-center justify-between p-4 ${THEME_TOKENS.radius.card} hover:bg-secondary/5 transition-colors group`}>
              <div className="flex items-center gap-4">
                <div className={`w-2 h-2 rounded-full ${activity.type === 'memo' ? 'bg-beige' : 'bg-success shadow-[0_0_10px_rgba(34,197,94,0.3)]'}`} />
                <div>
                  <p className="font-bold text-foreground group-hover:text-beige transition-colors">{activity.action}</p>
                  <p className={THEME_TOKENS.typography.capsLabel}>{activity.company}</p>
                </div>
              </div>
              <span className={THEME_TOKENS.typography.capsLabel}>{activity.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default UsagePage;
