import { BarChart3, Mic, Clock, TrendingUp } from "lucide-react";

const UsagePage = () => {
  const stats = [
    {
      icon: Mic,
      label: "Total Memos",
      value: "127",
      change: "+12 this week",
      color: "text-primary",
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
      color: "text-primary",
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
    <div className="max-w-4xl mx-auto space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Usage Analytics</h1>
        <p className="text-muted-foreground">Track your voice memo activity and CRM updates</p>
      </div>

      {/* Stats Grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-card rounded-2xl shadow-soft p-5">
            <div className="flex items-center gap-3 mb-3">
              <div className={`w-10 h-10 rounded-xl bg-secondary flex items-center justify-center`}>
                <stat.icon className={`h-5 w-5 ${stat.color}`} />
              </div>
            </div>
            <p className="text-2xl font-bold text-foreground">{stat.value}</p>
            <p className="text-sm text-muted-foreground">{stat.label}</p>
            <p className="text-xs text-success mt-1">{stat.change}</p>
          </div>
        ))}
      </div>

      {/* Weekly Chart */}
      <div className="bg-card rounded-2xl shadow-soft p-6">
        <h2 className="text-lg font-semibold text-foreground mb-6">This Week</h2>
        
        <div className="flex items-end justify-between gap-2 h-48">
          {weeklyData.map((day) => (
            <div key={day.day} className="flex-1 flex flex-col items-center gap-2">
              <div className="w-full flex items-end justify-center h-36">
                <div 
                  className="w-full max-w-[40px] bg-primary/20 rounded-t-lg transition-all hover:bg-primary/30"
                  style={{ 
                    height: day.memos > 0 ? `${(day.memos / maxMemos) * 100}%` : '4px',
                    minHeight: '4px'
                  }}
                >
                  <div 
                    className="w-full bg-primary rounded-t-lg"
                    style={{ height: '100%' }}
                  />
                </div>
              </div>
              <div className="text-center">
                <p className="text-xs font-medium text-foreground">{day.memos}</p>
                <p className="text-xs text-muted-foreground">{day.day}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-card rounded-2xl shadow-soft p-6">
        <h2 className="text-lg font-semibold text-foreground mb-6">Recent Activity</h2>
        
        <div className="space-y-4">
          {[
            { action: "Created memo", company: "Acme Corp", time: "2 hours ago" },
            { action: "Updated deal", company: "TechStart Inc", time: "5 hours ago" },
            { action: "Created contact", company: "Global Solutions", time: "1 day ago" },
            { action: "Created memo", company: "InnovateCo", time: "2 days ago" },
            { action: "Updated deal", company: "NextGen Systems", time: "3 days ago" },
          ].map((activity, i) => (
            <div key={i} className="flex items-center justify-between py-3 border-b border-border last:border-0">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-primary" />
                <div>
                  <p className="font-medium text-foreground">{activity.action}</p>
                  <p className="text-sm text-muted-foreground">{activity.company}</p>
                </div>
              </div>
              <span className="text-xs text-muted-foreground">{activity.time}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default UsagePage;
