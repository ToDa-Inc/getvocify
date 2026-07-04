import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";

const TermsPage = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-24">
        <h1 className="text-4xl font-black mb-4 tracking-tight">Terms of Service</h1>
        <p className="text-muted-foreground mb-12">Last Updated: March 1, 2026</p>

        <div className="prose prose-slate max-w-none space-y-12">
          <section>
            <h2 className="text-2xl font-bold mb-4">1. Agreement</h2>
            <p className="text-lg leading-relaxed text-muted-foreground">
              By accessing or using Vocify (&quot;Service&quot;), operated by Vocify (&quot;we,&quot; &quot;us&quot;), you
              agree to these Terms. If you do not agree, do not use the Service.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">2. The Service</h2>
            <p className="text-muted-foreground mb-4">
              Vocify provides tools to record voice input, transcribe and extract structured data, and—with your
              approval—update connected CRM systems. Features and availability may change with reasonable notice where
              required by law.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">3. Accounts</h2>
            <p className="text-muted-foreground mb-4">
              You must provide accurate registration information and safeguard your credentials. You are responsible for
              activity under your account. Notify us promptly of unauthorized use.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">4. Acceptable use</h2>
            <ul className="list-disc pl-6 space-y-3 text-muted-foreground">
              <li>Use the Service only in compliance with applicable laws and your agreements with third parties (e.g. CRM providers).</li>
              <li>Do not misuse the Service, attempt unauthorized access, or interfere with other users.</li>
              <li>Do not submit unlawful, infringing, or harmful content through recordings or text.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">5. Subscriptions &amp; trials</h2>
            <p className="text-muted-foreground">
              Paid plans, trials, and billing terms will be presented at checkout or in your account. Taxes may apply.
              Cancellation and refund rules follow the terms shown at purchase or as required by law.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">6. Disclaimers</h2>
            <p className="text-muted-foreground">
              The Service is provided &quot;as is&quot; to the fullest extent permitted by law. AI-generated suggestions
              may be imperfect; you remain responsible for reviewing and approving updates to your CRM.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">7. Limitation of liability</h2>
            <p className="text-muted-foreground">
              To the maximum extent permitted by law, we are not liable for indirect, incidental, or consequential
              damages, or for loss of profits or data, except where liability cannot be excluded by law.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">8. Changes</h2>
            <p className="text-muted-foreground">
              We may update these Terms. We will post the new date above; continued use after changes constitutes
              acceptance where permitted by law.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">9. Contact</h2>
            <p className="text-muted-foreground">
              Questions:{" "}
              <a href="mailto:toni@getvocify.com" className="text-beige font-semibold hover:underline">
                toni@getvocify.com
              </a>
            </p>
          </section>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default TermsPage;
