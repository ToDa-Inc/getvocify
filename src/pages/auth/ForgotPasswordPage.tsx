import { useState } from "react";
import { Link } from "react-router-dom";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi } from "@/features/auth/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const ForgotPasswordPage = () => {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await authApi.requestPasswordReset(email.trim());
      setSent(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream px-6">
      <div className={`w-full max-w-md ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 space-y-6`}>
        <div className="text-center">
          <Logo size="sm" className="mx-auto mb-4" />
          <h1 className={THEME_TOKENS.typography.sectionTitle}>Reset password</h1>
        </div>
        {sent ? (
          <p className="text-sm text-muted-foreground text-center">
            If an account exists for that email, we sent a reset link.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              type="email"
              required
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Button type="submit" className="w-full" disabled={loading}>
              Send reset link
            </Button>
          </form>
        )}
        <Link to="/login" className="block text-center text-sm text-beige hover:underline">
          Back to login
        </Link>
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
