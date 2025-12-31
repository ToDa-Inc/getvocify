import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Mic, ArrowRight } from "lucide-react";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const LoginPage = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await login({ email, password });
      toast.success("Welcome back!");
      navigate("/dashboard");
    } catch (error: any) {
      toast.error(error.data?.detail || "Login failed. Please check your credentials.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-cream">
      <div className={`w-full max-w-md ${THEME_TOKENS.motion.fadeIn}`}>
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-3xl bg-beige/10 mb-6">
            <Mic className="h-8 w-8 text-beige" />
          </div>
          <h1 className={`${THEME_TOKENS.typography.pageTitle} mb-2`}>Welcome Back</h1>
          <p className={THEME_TOKENS.typography.body}>Login to your Vocify account</p>
        </div>

        <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-10`}>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="email" className={THEME_TOKENS.typography.capsLabel}>Email Address</Label>
              <Input
                id="email"
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="h-12 bg-secondary/5 border-border/40 focus:border-beige"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className={THEME_TOKENS.typography.capsLabel}>Password</Label>
                <Link to="/forgot-password" hidden className="text-[10px] font-black uppercase tracking-widest text-beige hover:underline">
                  Forgot?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="h-12 bg-secondary/5 border-border/40 focus:border-beige"
              />
            </div>

            <Button
              type="submit"
              className="w-full h-12 rounded-full bg-beige text-cream hover:bg-beige/90 transition-all group"
              disabled={isLoading}
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-cream border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <span className="font-bold">Log In</span>
                  <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </Button>
          </form>

          <div className="mt-8 text-center">
            <p className="text-sm text-muted-foreground">
              Don't have an account?{" "}
              <Link to="/signup" className="font-bold text-beige hover:underline">
                Sign Up
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;

