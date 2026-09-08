import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import Logo from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authApi } from "@/features/auth/api";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const ResetPasswordPage = () => {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await authApi.setNewPassword(token, password);
      navigate("/login", { replace: true });
    } catch {
      setError("Could not reset password. The link may have expired.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream px-6">
      <div className={`w-full max-w-md ${THEME_TOKENS.cards.base} ${THEME_TOKENS.radius.card} p-8 space-y-6`}>
        <div className="text-center">
          <Logo size="sm" className="mx-auto mb-4" />
          <h1 className={THEME_TOKENS.typography.sectionTitle}>Choose a new password</h1>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            type="password"
            required
            minLength={8}
            placeholder="New password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Input
            type="password"
            required
            minLength={8}
            placeholder="Confirm password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={loading}>
            Update password
          </Button>
        </form>
        <Link to="/login" className="block text-center text-sm text-beige hover:underline">
          Back to login
        </Link>
      </div>
    </div>
  );
};

export default ResetPasswordPage;
