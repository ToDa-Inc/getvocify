import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Mic, Search, Calendar, Clock, AlertCircle } from "lucide-react";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { Input } from "@/components/ui/input";
import { memosApi } from "@/features/memos/api";
import { formatDistanceToNow } from "date-fns";

const getStatusBadge = (status: string) => {
  switch (status) {
    case "approved":
      return (
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest bg-success/10 text-success`}>
          <span className="w-1.5 h-1.5 rounded-full bg-success shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
          Approved
        </span>
      );
    case "pending_review":
      return (
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest bg-warning/10 text-warning`}>
          <span className="w-1.5 h-1.5 rounded-full bg-warning shadow-[0_0_8px_rgba(234,179,8,0.4)]" />
          Pending
        </span>
      );
    case "pending_transcript":
      return (
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest bg-beige/10 text-beige`}>
          <span className="w-1.5 h-1.5 rounded-full bg-beige" />
          Review transcript
        </span>
      );
    case "uploading":
    case "transcribing":
    case "extracting":
      return (
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest bg-secondary/20 text-muted-foreground`}>
          <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-pulse" />
          Processing
        </span>
      );
    case "failed":
      return (
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest bg-destructive/10 text-destructive`}>
          <span className="w-1.5 h-1.5 rounded-full bg-destructive shadow-[0_0_8px_rgba(239,68,68,0.4)]" />
          Failed
        </span>
      );
    default:
      return null;
  }
};

const MemosPage = () => {
  const [memos, setMemos] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");

  const fetchMemos = async () => {
    try {
      const data = await memosApi.list({ limit: 500 });
      setMemos(data);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch memos:", err);
      setError("Could not load your conversations.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchMemos();
    // Refresh every 10 seconds to catch status updates
    const interval = setInterval(fetchMemos, 10000);
    return () => clearInterval(interval);
  }, []);

  const filteredMemos = memos.filter(memo => {
    if (!searchTerm.trim()) return true;
    const q = searchTerm.toLowerCase().trim();
    const company = (memo.extraction?.companyName || "").toLowerCase();
    const transcript = (memo.transcript || "").toLowerCase();
    const summary = (memo.extraction?.summary || "").toLowerCase();
    return company.includes(q) || transcript.includes(q) || summary.includes(q);
  });

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className={`max-w-4xl mx-auto ${THEME_TOKENS.motion.fadeIn}`}>
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
        <div className={V_PATTERNS.dashboardHeader}>
          <h1 className={THEME_TOKENS.typography.pageTitle}>
            Voice <span className={THEME_TOKENS.typography.accentTitle}>Memos</span>
          </h1>
          <p className={THEME_TOKENS.typography.body}>Manage and review your sales conversations.</p>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40 group-focus-within:text-beige transition-colors" />
            <Input 
              placeholder="Search memos..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-11 pr-6 h-12 bg-white border-border/40 rounded-full w-full md:w-64 focus:ring-beige focus:border-beige transition-all shadow-soft"
            />
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-4">
          <div className="w-8 h-8 border-2 border-beige border-t-transparent rounded-full animate-spin" />
          <p className={THEME_TOKENS.typography.capsLabel}>Syncing conversations...</p>
        </div>
      ) : error ? (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-12 text-center`}>
          <AlertCircle className="h-10 w-10 text-destructive mx-auto mb-4" />
          <p className="text-muted-foreground">{error}</p>
          <button onClick={fetchMemos} className="mt-4 text-[10px] font-black uppercase tracking-widest text-beige hover:underline">
            Try again
          </button>
        </div>
      ) : filteredMemos.length === 0 ? (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-20 text-center`}>
          <div className={`w-20 h-20 mx-auto mb-8 rounded-3xl bg-secondary/5 flex items-center justify-center`}>
            <Mic className="h-10 w-10 text-muted-foreground/20" />
          </div>
          <h3 className="text-2xl font-bold text-foreground mb-4">
            {searchTerm ? "No matches found" : "No voice memos yet"}
          </h3>
          <p className="text-muted-foreground mb-10 max-w-sm mx-auto leading-relaxed">
            {searchTerm ? `No results for "${searchTerm}"` : "Your recorded conversations will appear here once processed."}
          </p>
          {!searchTerm && (
            <Link 
              to="/dashboard/record"
              className="inline-flex items-center gap-3 px-10 py-4 bg-beige text-cream rounded-full font-black uppercase tracking-widest shadow-large hover:scale-105 transition-transform"
            >
              <Mic className="h-5 w-5" />
              Record First Memo
            </Link>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {filteredMemos.map((memo) => (
            <Link
              key={memo.id}
              to={`/dashboard/memos/${memo.id}`}
              className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} ${THEME_TOKENS.cards.hover} ${V_PATTERNS.listItem} group`}
            >
              <div className="flex items-center gap-8">
                <div className={`w-14 h-14 rounded-2xl bg-secondary/5 flex items-center justify-center flex-shrink-0 group-hover:bg-beige/10 transition-colors`}>
                  <Mic className="h-6 w-6 text-beige" />
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="font-bold text-foreground text-lg group-hover:text-beige transition-colors truncate">
                      {memo.extraction?.companyName || "Untitled Conversation"}
                    </h3>
                    <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/30 bg-secondary/20 px-2 py-0.5 rounded-md flex items-center gap-1">
                      <Clock className="h-2.5 w-2.5" />
                      {formatDuration(memo.audioDuration)}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-1 leading-relaxed">
                    {memo.transcript || "Conversation being transcribed..."}
                  </p>
                </div>
                
                <div className="flex flex-col items-end gap-3 flex-shrink-0">
                  {getStatusBadge(memo.status)}
                  <div className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest text-muted-foreground/40">
                    <Calendar className="h-3 w-3" />
                    {formatDistanceToNow(new Date(memo.createdAt), { addSuffix: true })}
                  </div>
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
