import { Link } from "react-router-dom";
import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";
import { Button } from "@/components/ui/button";
import { APP_URL } from "@/lib/app-url";

const BlogPage = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-24">
        <h1 className="text-4xl font-black mb-4 tracking-tight">Blog</h1>
        <p className="text-muted-foreground mb-12 text-lg">
          Product updates, CRM tips, and voice-to-workflow ideas—coming soon.
        </p>

        <div
          className="rounded-2xl border border-border/50 bg-muted/30 p-10 md:p-14 text-center space-y-6"
        >
          <p className="text-foreground font-medium text-lg">
            We&apos;re preparing articles and release notes. In the meantime, try Vocify and tell us what you&apos;d like
            to read about.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <Button variant="hero" className="rounded-full" asChild>
              <a href={`${APP_URL}/signup`}>Start free trial</a>
            </Button>
            <Button variant="outline" className="rounded-full" asChild>
              <a href="mailto:toni@getvocify.com">Suggest a topic</a>
            </Button>
          </div>
        </div>

        <p className="mt-10">
          <Link to="/" className="text-sm text-beige font-semibold hover:underline">
            ← Back to home
          </Link>
        </p>
      </main>
      <Footer />
    </div>
  );
};

export default BlogPage;
