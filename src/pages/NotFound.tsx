import { useLocation } from "react-router-dom";
import { useEffect } from "react";
import { useAuth } from "@/features/auth";

const NotFound = () => {
  const location = useLocation();
  const { hasStoredSession, logout } = useAuth();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted">
      <div className="text-center">
        <h1 className="mb-4 text-4xl font-bold">404</h1>
        <p className="mb-4 text-xl text-muted-foreground">Oops! Page not found</p>
        <div className="flex flex-col items-center gap-3">
          <a href="/" className="text-primary underline hover:text-primary/90">
            Return to Home
          </a>
          {hasStoredSession ? (
            <button
              type="button"
              data-testid="session-sign-out"
              className="text-[10px] font-black uppercase tracking-widest text-muted-foreground hover:text-foreground hover:underline"
              onClick={async () => {
                await logout();
                window.location.replace("/login");
              }}
            >
              Sign out
            </button>
          ) : (
            <a href="/login" className="text-[10px] font-black uppercase tracking-widest text-muted-foreground hover:underline">
              Go to login
            </a>
          )}
        </div>
      </div>
    </div>
  );
};

export default NotFound;
