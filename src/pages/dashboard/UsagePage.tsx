import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { BarChart3, Mic, Clock, TrendingUp } from "lucide-react";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { memosApi, memoKeys } from "@/features/memos/api";

const UsagePage = () => {
  const { data: usage, isLoading } = useQuery({
    queryKey: memoKeys.usage(),
    queryFn: () => memosApi.getUsage(),
  });

  const stats = usage
    ? [
        {
          icon: Mic,
          label: "Total Memos",
          value: String(usage.total_memos),
          change: usage.this_week_memos > 0 ? `+${usage.this_week_memos} this week` : "No memos this week",
          color: "text-beige",
        },
        {
          icon: Clock,
          label: "Time Saved",
          value: `${usage.time_saved_hours} hrs`,
          change: usage.this_week_time_saved_hours > 0 ? `+${usage.this_week_time_saved_hours} hrs this week` : "—",
          color: "text-success",
        },
        {
          icon: BarChart3,
          label: "CRM Updates",
          value: String(usage.approved_count),
          change: usage.this_week_approved > 0 ? `+${usage.this_week_approved} this week` : "—",
          color: "text-warning",
        },
        {
          icon: TrendingUp,
          label: "Accuracy Rate",
          value: usage.accuracy_pct != null ? `${usage.accuracy_pct}%` : "—",
          change: usage.accuracy_pct != null ? "Approved / (Approved + Rejected)" : "No data yet",
          color: "text-beige",
        },
      ]
    : [];

  const weeklyData = usage?.weekly ?? [];
  const maxMemos = weeklyData.length ? Math.max(...weeklyData.map((d) => d.memos), 1) : 1;
  const recentActivity = usage?.recent_activity ?? [];

  if (isLoading) {
    return (
      <div className={`max-w-5xl mx-auto space-y-10 ${THEME_TOKENS.motion.fadeIn}`}>
        <div className={V_PATTERNS.dashboardHeader}>
          <h1 className={THEME_TOKENS.typography.pageTitle}>
            Usage <span className={THEME_TOKENS.typography.accentTitle}>Analytics</span>
          </h1>
          <p className={THEME_TOKENS.typography.body}>Track your performance and time saved with Vocify.</p>
        </div>
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-12 text-center`}>
          <div className="w-8 h-8 border-2 border-beige border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className={THEME_TOKENS.typography.capsLabel}>Loading analytics...</p>
        </div>
      </div>
    );
  }

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
            <div className="w-12 h-12 rounded-2xl bg-secondary/5 flex items-center justify-center mb-6">
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
                    height: day.memos > 0 ? `${(day.memos / maxMemos) * 100}%` : "8px",
                  }}
                >
                  {day.memos > 0 && (
                    <div className="absolute inset-0 bg-beige rounded-t-2xl shadow-[0_0_20px_rgba(245,215,176,0.3)]" />
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
          {recentActivity.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">No activity yet.</p>
          ) : (
            recentActivity.slice(0, 10).map((activity, i) => (
              <div key={i} className={`flex items-center justify-between p-4 ${THEME_TOKENS.radius.card} hover:bg-secondary/5 transition-colors group`}>
                <div className="flex items-center gap-4">
                  <div className={`w-2 h-2 rounded-full ${activity.type === "memo" ? "bg-beige" : "bg-success shadow-[0_0_10px_rgba(34,197,94,0.3)]"}`} />
                  <div>
                    <p className="font-bold text-foreground group-hover:text-beige transition-colors">{activity.action}</p>
                    <p className={THEME_TOKENS.typography.capsLabel}>{activity.company}</p>
                  </div>
                </div>
                <span className={THEME_TOKENS.typography.capsLabel}>
                  {formatDistanceToNow(new Date(activity.time), { addSuffix: true })}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default UsagePage;
