import { Link } from "react-router-dom";
import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";
import { Button } from "@/components/ui/button";
import { APP_URL } from "@/lib/app-url";

const AboutPage = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-24">
        <h1 className="text-4xl font-black mb-4 tracking-tight">About Vocify</h1>
        <p className="text-muted-foreground mb-12 text-lg">
          We&apos;re building the voice-first way to keep your CRM accurate—without the typing tax.
        </p>

        <div className="space-y-10 text-muted-foreground leading-relaxed">
          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">Our mission</h2>
            <p>
              Sales teams lose hours every week retyping meeting notes. Vocify turns what you say into structured CRM
              updates in about a minute, so you can stay in the field instead of fighting your laptop.
            </p>
          </section>
          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">What we believe</h2>
            <ul className="list-disc pl-6 space-y-2">
              <li>Your pipeline should reflect reality, not what you remembered to type at 6pm.</li>
              <li>Voice is the fastest input when you&apos;re between meetings or in the car.</li>
              <li>You stay in control: review and approve before anything hits your CRM.</li>
            </ul>
          </section>
          <section>
            <h2 className="text-2xl font-bold text-foreground mb-4">Contact</h2>
            <p>
              Questions or partnerships:{" "}
              <a href="mailto:toni@getvocify.com" className="text-beige font-semibold hover:underline">
                toni@getvocify.com
              </a>
            </p>
          </section>
        </div>

        <div className="mt-14">
          <Button variant="hero" size="lg" className="rounded-full" asChild>
            <a href={`${APP_URL}/signup`}>Start free trial</a>
          </Button>
          <Button variant="link" className="ml-4" asChild>
            <Link to="/">Back to home</Link>
          </Button>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default AboutPage;
