import { useEffect, useState } from "react";
import { Link, Outlet } from "react-router-dom";
import { Lock } from "lucide-react";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import {
  clearStoredAdminMasterKey,
  getStoredAdminMasterKey,
  setStoredAdminMasterKey,
} from "@/lib/admin-auth";
import { adminApi } from "@/features/admin/api";
import { ApiError } from "@/shared/lib/api-client";

const AdminLayout = () => {
  const [unlocked, setUnlocked] = useState(() => !!getStoredAdminMasterKey());
  const [keyInput, setKeyInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    if (!unlocked) return;
    setChecking(true);
    adminApi
      .runtime()
      .then(() => setError(null))
      .catch((err: unknown) => {
        if (err instanceof ApiError) {
          if (err.status === 401) {
            clearStoredAdminMasterKey();
            setUnlocked(false);
            setError("Invalid master key");
            return;
          }
          if (err.status === 503) {
            setError("Admin is not configured on the backend");
            return;
          }
        }
        setError("Could not reach admin API");
      })
      .finally(() => setChecking(false));
  }, [unlocked]);

  const handleUnlock = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = keyInput.trim();
    if (!trimmed) return;
    setStoredAdminMasterKey(trimmed);
    setChecking(true);
    setError(null);
    try {
      await adminApi.runtime();
      setUnlocked(true);
      setKeyInput("");
    } catch (err: unknown) {
      clearStoredAdminMasterKey();
      setUnlocked(false);
      if (err instanceof ApiError) {
        if (err.status === 503) {
          setError("Admin is not configured on the backend");
        } else {
          setError("Invalid master key");
        }
      } else {
        setError("Could not reach admin API");
      }
    } finally {
      setChecking(false);
    }
  };

  const handleLock = () => {
    clearStoredAdminMasterKey();
    setUnlocked(false);
    setKeyInput("");
    setError(null);
  };

  if (!unlocked) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center p-6">
        <div className={`w-full max-w-md ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.container} p-8 space-y-6`}>
          <div className="flex items-center gap-3">
            <Logo size="sm" />
            <div>
              <h1 className={THEME_TOKENS.typography.sectionTitle}>Admin</h1>
              <p className={THEME_TOKENS.typography.capsLabel}>Master key required</p>
            </div>
          </div>
          <form onSubmit={handleUnlock} className="space-y-4">
            <Input
              type="password"
              placeholder="Master key"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              autoComplete="off"
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full bg-beige text-cream hover:bg-beige-dark" disabled={checking}>
              {checking ? "Checking…" : "Unlock"}
            </Button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-cream">
      <header className="border-b border-border/60 bg-background/80 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Logo size="sm" />
            <span className={THEME_TOKENS.typography.sectionTitle}>Admin</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" asChild>
              <Link to="/admin">Accounts</Link>
            </Button>
            <Button variant="outline" size="sm" onClick={handleLock} className="gap-1.5">
              <Lock className="h-3.5 w-3.5" />
              Lock
            </Button>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto p-6 md:p-8">
        {checking ? (
          <p className={THEME_TOKENS.typography.capsLabel}>Verifying admin access…</p>
        ) : error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : (
          <Outlet />
        )}
      </main>
    </div>
  );
};

export default AdminLayout;
