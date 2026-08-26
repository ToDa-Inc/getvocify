import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Mic, Search, Calendar, Clock, AlertCircle } from "lucide-react";
import { THEME_TOKENS, V_PATTERNS } from "@/lib/theme/tokens";
import { Input } from "@/components/ui/input";
import { VocifyLoader } from "@/components/ui/vocify-loader";
import { memosApi } from "@/features/memos/api";
import { memoListSubtitle, memoListTitle } from "@/lib/copilot-note";
import { formatRecordedAtLabel } from "@/lib/memo-dates";
import { formatDistanceToNow } from "date-fns";

const getStatusBadge = (status: string) => {
  switch (status) {
    case "approved":
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-success/10 text-success">
          Approved
        </span>
      );
    case "pending_review":
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-warning/10 text-warning">
          Pending
        </span>
      );
    case "pending_transcript":
    case "uploading":
    case "transcribing":
    case "extracting":
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-secondary text-muted-foreground">
          Processing
        </span>
      );
    case "failed":
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-destructive/10 text-destructive">
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
    const contact = (memo.extraction?.contactName || "").toLowerCase();
    const company = (memo.extraction?.companyName || "").toLowerCase();
    const transcript = (memo.transcript || "").toLowerCase();
    const summary = (memo.extraction?.summary || "").toLowerCase();
    return contact.includes(q) || company.includes(q) || transcript.includes(q) || summary.includes(q);
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
              className="pl-11 pr-6 h-10 bg-card border-border rounded-lg w-full md:w-64"
            />
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20">
          <VocifyLoader size="md" label="Syncing conversations..." />
        </div>
      ) : error ? (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-12 text-center`}>
          <AlertCircle className="h-10 w-10 text-destructive mx-auto mb-4" />
          <p className="text-muted-foreground">{error}</p>
          <button onClick={fetchMemos} className="mt-4 text-sm font-medium text-beige hover:underline">
            Try again
          </button>
        </div>
      ) : filteredMemos.length === 0 ? (
        <div className={`${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-16 text-center`}>
          <div className="w-14 h-14 mx-auto mb-6 rounded-2xl bg-secondary flex items-center justify-center">
            <Mic className="h-6 w-6 text-muted-foreground/40" />
          </div>
          <h3 className="text-xl font-normal text-foreground mb-2">
            {searchTerm ? "No matches found" : "No voice memos yet"}
          </h3>
          <p className="text-muted-foreground mb-8 max-w-sm mx-auto leading-relaxed">
            {searchTerm ? `No results for "${searchTerm}"` : "Your recorded conversations will appear here once processed."}
          </p>
          {!searchTerm && (
            <Link 
              to="/dashboard/record"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-beige text-cream rounded-full font-normal"
            >
              <Mic className="h-4 w-4" />
              Record first memo
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
                <div className={`w-11 h-11 rounded-xl bg-secondary flex items-center justify-center flex-shrink-0`}>
                  <Mic className="h-5 w-5 text-beige" />
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="font-normal text-foreground text-[15px] truncate">
                      {memoListTitle(memo)}
                    </h3>
                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDuration(memo.audioDuration)}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-1 leading-relaxed">
                    {memoListSubtitle(memo) ||
                      (memo.extraction?.summary
                        ? String(memo.extraction.summary).replace(/^#+\s+/gm, " ").replace(/\s+/g, " ").trim()
                        : memo.transcript) ||
                      "Extracting CRM fields..."}
                  </p>
                </div>
                
                <div className="flex flex-col items-end gap-3 flex-shrink-0">
                  {getStatusBadge(memo.status)}
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground text-right max-w-[11rem]">
                    <Calendar className="h-3 w-3 flex-shrink-0" />
                    <span className="leading-snug">
                      {formatRecordedAtLabel(memo.createdAt) ||
                        formatDistanceToNow(new Date(memo.createdAt), { addSuffix: true })}
                    </span>
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
