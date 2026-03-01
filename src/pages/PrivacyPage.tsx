import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";

const PrivacyPage = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-24">
        <h1 className="text-4xl font-black mb-4 tracking-tight">Privacy Policy</h1>
        <p className="text-muted-foreground mb-12">Last Updated: March 1, 2026</p>

        <div className="prose prose-slate max-w-none space-y-12">
          <section>
            <h2 className="text-2xl font-bold mb-4">1. Introduction</h2>
            <p className="text-lg leading-relaxed text-muted-foreground">
              Vocify ("we," "us," or "our") provides a Chrome Extension designed to help sales professionals update their CRM via voice memos. We are committed to protecting your privacy and ensuring transparency in how we handle your data.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">2. Data We Collect</h2>
            <p className="text-muted-foreground mb-4">To provide our service, we collect the following information:</p>
            <ul className="list-disc pl-6 space-y-3 text-muted-foreground">
              <li>
                <strong className="text-foreground">Authentication Information:</strong> We collect your email address and store encrypted authentication tokens (Access/Refresh tokens) to manage your account and secure your session.
              </li>
              <li>
                <strong className="text-foreground">Audio Data:</strong> When you explicitly initiate a recording, we capture your voice via the Chrome Offscreen API. This audio is streamed securely to our backend for transcription and CRM field extraction.
              </li>
              <li>
                <strong className="text-foreground">Contextual Data (URL):</strong> We read the URL of the active tab only when a recording is active to identify relevant CRM records (e.g., HubSpot Deal IDs) for automatic association.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">3. How We Use Your Data</h2>
            <p className="text-muted-foreground mb-4">We use the collected data strictly for the following purposes:</p>
            <ul className="list-disc pl-6 space-y-3 text-muted-foreground">
              <li>To authenticate your identity and provide access to your Vocify account.</li>
              <li>To transcribe your voice memos into text and extract relevant CRM fields using AI.</li>
              <li>To automate the association of voice memos with the correct records in your CRM.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">4. Data Protection & Security</h2>
            <ul className="list-disc pl-6 space-y-3 text-muted-foreground">
              <li>
                <strong className="text-foreground">No Sale of Data:</strong> We do not sell, rent, or trade your personal data, audio recordings, or CRM information to any third parties.
              </li>
              <li>
                <strong className="text-foreground">Encryption:</strong> All data is transmitted over secure, encrypted channels (HTTPS/WSS) to our production API at api.getvocify.com.
              </li>
              <li>
                <strong className="text-foreground">Limited Use:</strong> Our use of information received from Google APIs will adhere to the Chrome Web Store User Data Policy, including the Limited Use requirements.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">5. Third-Party Services</h2>
            <p className="text-muted-foreground mb-4">We use industry-standard sub-processors for core functionality:</p>
            <ul className="list-disc pl-6 space-y-3 text-muted-foreground">
              <li>
                <strong className="text-foreground">Transcription:</strong> Audio is processed via secure transcription providers (e.g., Speechmatics/Deepgram) solely for converting speech to text.
              </li>
              <li>
                <strong className="text-foreground">AI Extraction:</strong> Transcripts are processed via secure LLM providers to identify CRM field updates.
              </li>
              <li>
                <strong className="text-foreground">CRM Integration:</strong> Data is sent to your connected CRM (e.g., HubSpot) only upon your explicit confirmation within the extension UI.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">6. Your Choices</h2>
            <p className="text-muted-foreground">
              You can stop all collection of information by the extension by uninstalling it. You may also request the deletion of your account and associated data by contacting us at support@getvocify.com.
            </p>
          </section>

          <section className="pt-12 border-t">
            <h2 className="text-2xl font-bold mb-4">7. Contact Us</h2>
            <p className="text-muted-foreground">
              If you have any questions about this Privacy Policy, please contact:<br />
              <span className="font-bold text-foreground">Email:</span> support@getvocify.com<br />
              <span className="font-bold text-foreground">Website:</span> https://getvocify.com
            </p>
          </section>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default PrivacyPage;
