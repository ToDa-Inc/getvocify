import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/features/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Mic, ArrowRight } from "lucide-react";
import { THEME_TOKENS } from "@/lib/theme/tokens";

const SignupPage = () => {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { signup } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await signup({ fullName, email, password, companyName });
      toast.success("Account created successfully!");
      navigate("/dashboard");
    } catch (error: any) {
      toast.error(error.data?.detail || "Signup failed. Please try again.");
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
          <h1 className={`${THEME_TOKENS.typography.pageTitle} mb-2`}>Join Vocify</h1>
          <p className={THEME_TOKENS.typography.body}>Start transcribing your voice to CRM</p>
        </div>

        <div className={`${THEME_TOKENS.cards.premium} ${THEME_TOKENS.radius.card} p-10`}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="fullName" className={THEME_TOKENS.typography.capsLabel}>Full Name</Label>
              <Input
                id="fullName"
                placeholder="John Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                className="h-12 bg-secondary/5 border-border/40 focus:border-beige"
              />
            </div>
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
              <Label htmlFor="companyName" className={THEME_TOKENS.typography.capsLabel}>Company (Optional)</Label>
              <Input
                id="companyName"
                placeholder="Acme Inc."
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="h-12 bg-secondary/5 border-border/40 focus:border-beige"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className={THEME_TOKENS.typography.capsLabel}>Password</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                className="h-12 bg-secondary/5 border-border/40 focus:border-beige"
              />
            </div>

            <Button
              type="submit"
              className="w-full h-12 rounded-full bg-beige text-cream hover:bg-beige/90 transition-all group mt-4"
              disabled={isLoading}
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-cream border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <span className="font-bold">Create Account</span>
                  <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </Button>
          </form>

          <div className="mt-8 text-center">
            <p className="text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link to="/login" className="font-bold text-beige hover:underline">
                Log In
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SignupPage;

