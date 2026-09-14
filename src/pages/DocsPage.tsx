import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";
import { APP_URL } from "@/lib/app-url";

const SETTINGS_CRM = `${APP_URL}/dashboard/settings`;
const SETTINGS_CALLING = `${APP_URL}/dashboard/settings/calling`;
const SETTINGS_BILLING = `${APP_URL}/dashboard/settings/billing`;
const RECORD = `${APP_URL}/dashboard/record`;
const PROFILE = `${APP_URL}/dashboard/profile`;
const UNINSTALL_KB =
  "https://knowledge.hubspot.com/marketplace/install-apps-in-the-hubspot-marketplace";

const SCOPE_ROWS = [
  {
    object: "Contacts",
    direction: "Bidirectional",
    detail:
      "Vocify reads the contact you are working on and can create or update name, phone, email, job title, lead status, and other fields you allow.",
  },
  {
    object: "Companies",
    direction: "Bidirectional",
    detail:
      "Vocify reads the associated company and can create or update name, domain, industry, and other fields you allow.",
  },
  {
    object: "Deals",
    direction: "Bidirectional",
    detail:
      "Vocify reads the deal on the page or in the memo and can create or update amount, stage, close date, next step, and other fields you allow.",
  },
  {
    object: "Line items",
    direction: "Bidirectional",
    detail:
      "Vocify reads and can write line items on a deal when those scopes are granted and you enable the fields.",
  },
  {
    object: "Owners",
    direction: "HubSpot → Vocify",
    detail:
      "Vocify reads HubSpot owners so activities and records can be credited to the right salesperson. Vocify does not edit owner records.",
  },
];

const Section = ({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) => (
  <section id={id} className="scroll-mt-28 space-y-4">
    <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
    {children}
  </section>
);

const DocsPage = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-24">
        <p className="text-[11px] font-medium uppercase tracking-[0.25em] text-muted-foreground mb-4">
          HubSpot Marketplace · setup guide
        </p>
        <h1 className="text-4xl font-black mb-4 tracking-tight">
          Vocify setup guide for HubSpot
        </h1>
        <p className="text-muted-foreground mb-4 text-lg leading-relaxed">
          This page is the setup guide for the Vocify listing on the HubSpot
          Marketplace. It covers install, configuration, daily use, disconnect,
          and uninstall — only for HubSpot.
        </p>
        <p className="text-sm text-muted-foreground mb-12">
          Last updated: 14 September 2026 · Support:{" "}
          <a
            href="mailto:support@getvocify.com"
            className="text-beige font-semibold hover:underline"
          >
            support@getvocify.com
          </a>
        </p>

        <nav
          aria-label="On this page"
          className="mb-16 rounded-2xl border border-border/70 bg-card p-6"
        >
          <p className="text-[13px] text-muted-foreground mb-3">On this page</p>
          <ol className="list-decimal pl-5 space-y-2 text-sm text-foreground">
            <li>
              <a href="#what-it-does" className="text-beige hover:underline">
                What Vocify does in HubSpot
              </a>
            </li>
            <li>
              <a href="#install" className="text-beige hover:underline">
                Install and connect
              </a>
            </li>
            <li>
              <a href="#configure" className="text-beige hover:underline">
                Configure
              </a>
            </li>
            <li>
              <a href="#use" className="text-beige hover:underline">
                Use Vocify
              </a>
            </li>
            <li>
              <a href="#shared-data" className="text-beige hover:underline">
                Shared data
              </a>
            </li>
            <li>
              <a href="#pricing" className="text-beige hover:underline">
                Pricing
              </a>
            </li>
            <li>
              <a href="#disconnect" className="text-beige hover:underline">
                Disconnect
              </a>
            </li>
            <li>
              <a href="#uninstall" className="text-beige hover:underline">
                Uninstall
              </a>
            </li>
          </ol>
        </nav>

        <div className="space-y-16 text-[15px] leading-relaxed text-muted-foreground">
          <Section id="what-it-does" title="What Vocify does in HubSpot">
            <p>
              Field reps and callers lose time — and pipeline visibility — when
              they retype notes into HubSpot between visits or after a call.
              Vocify is a sales copilot: you speak, it drafts the HubSpot
              update, and your director sees a CRM that matches the day.
            </p>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong className="text-foreground">Field sales.</strong> After a
                visit, send a voice note from WhatsApp, the Vocify dashboard, or
                the Chrome side panel. Vocify transcribes it and proposes
                contact, company, deal, and task updates for HubSpot.
              </li>
              <li>
                <strong className="text-foreground">Callers.</strong> Place the
                call from the Vocify dialer (Pro) or process a HubSpot call
                recording. Vocify fills the allowed fields, writes a note, opens
                follow-up tasks, and attaches the Call activity — including
                outcome and recording when the dialer is used — so nothing from
                the conversation is lost.
              </li>
            </ul>
            <p>
              Vocify does not replace HubSpot. It writes into your existing
              contacts, companies, deals, line items, tasks, and Call
              activities. Sales-objection coaching in the dashboard is a
              separate Vocify feature; it does not install HubSpot CRM cards.
            </p>
          </Section>

          <Section id="install" title="Install the app and connect HubSpot">
            <p>
              Vocify uses OAuth only. There is no private-app token paste.
              A workspace owner or admin must connect HubSpot.
            </p>
            <h3 className="text-lg font-bold text-foreground pt-2">
              From Vocify
            </h3>
            <ol className="list-decimal pl-6 space-y-3">
              <li>
                Create or log in to a Vocify workspace at{" "}
                <a href={APP_URL} className="text-beige font-semibold hover:underline">
                  app.getvocify.com
                </a>
                .
              </li>
              <li>
                Open{" "}
                <a href={SETTINGS_CRM} className="text-beige font-semibold hover:underline">
                  Settings → CRM
                </a>
                .
              </li>
              <li>
                On the HubSpot row, click <strong className="text-foreground">Connect</strong>.
              </li>
              <li>
                Click <strong className="text-foreground">Connect with HubSpot</strong>. You
                leave Vocify and land on HubSpot&apos;s account picker.
              </li>
              <li>
                Choose the HubSpot account that should receive the data.
              </li>
              <li>
                Review the permission screen. Vocify asks to read and write
                contacts, companies, deals, and line items; read CRM schemas
                for those objects; and read owners. Click{" "}
                <strong className="text-foreground">Connect app</strong>.
              </li>
              <li>
                HubSpot redirects you back to Vocify. Settings → CRM shows
                HubSpot as <strong className="text-foreground">Connected</strong>.
              </li>
            </ol>
            <h3 className="text-lg font-bold text-foreground pt-2">
              From the HubSpot Marketplace
            </h3>
            <ol className="list-decimal pl-6 space-y-3">
              <li>Open the Vocify listing and click Install.</li>
              <li>
                Sign in to Vocify if you are asked, then complete the same
                HubSpot permission screen as above.
              </li>
              <li>
                You return to Settings → CRM with HubSpot connected. Continue
                with configuration before you rely on automatic writes.
              </li>
            </ol>
            <p>
              If HubSpot later adds scopes (for example owners), do{" "}
              <strong className="text-foreground">not</strong> disconnect.
              Click the shield icon{" "}
              <strong className="text-foreground">Refresh HubSpot permissions</strong>{" "}
              on the HubSpot row. Disconnecting deletes saved field mapping and
              the sync audit trail for that connection.
            </p>
          </Section>

          <Section id="configure" title="Configure the app">
            <p>
              Still on{" "}
              <a href={SETTINGS_CRM} className="text-beige font-semibold hover:underline">
                Settings → CRM
              </a>
              , scroll to <strong className="text-foreground">HubSpot fields</strong>.
            </p>
            <ol className="list-decimal pl-6 space-y-3">
              <li>
                <strong className="text-foreground">New deals — pipeline and stage.</strong>{" "}
                Choose the default HubSpot pipeline and stage Vocify uses when
                a memo creates a deal.
              </li>
              <li>
                <strong className="text-foreground">Fields to fill.</strong> Open
                Deals, Contacts, Companies, and Line items. Enable only the
                properties Vocify may write. This is the “fields to select”
                screen. Leave a property off if you never want voice to touch
                it.
              </li>
              <li>
                <strong className="text-foreground">After each call.</strong>{" "}
                Leave <em>Skip Approve and write to CRM</em> off if every memo
                must show proposed changes first. Turn it on if Vocify should
                write the note, tasks, and allowed fields as soon as processing
                finishes (HubSpot recordings, the Vocify dialer, and memos
                already locked to a contact or deal). It does not change lead
                status, create deals, or write voicemail / no-answer stubs.
              </li>
              <li>
                Click <strong className="text-foreground">Save</strong>. A
                successful save is your configuration sync.
              </li>
            </ol>
            <p>
              Optional:{" "}
              <a href={SETTINGS_CALLING} className="text-beige font-semibold hover:underline">
                Settings → Calling
              </a>{" "}
              to verify a caller ID and set transcription language.{" "}
              <a href={PROFILE} className="text-beige font-semibold hover:underline">
                Profile
              </a>{" "}
              to store the WhatsApp number Vocify should match to this user.
            </p>
          </Section>

          <Section id="use" title="Use the app">
            <h3 className="text-lg font-bold text-foreground">
              Voice memo from the dashboard
            </h3>
            <ol className="list-decimal pl-6 space-y-3">
              <li>
                Open{" "}
                <a href={RECORD} className="text-beige font-semibold hover:underline">
                  Record
                </a>
                .
              </li>
              <li>
                Speak for about 30 seconds: who you met, the company, amount,
                and next step. A typical demo uses a test contact such as
                “Danny Test”.
              </li>
              <li>
                Vocify transcribes the audio and shows{" "}
                <strong className="text-foreground">proposed changes</strong>{" "}
                for HubSpot — fields, note, and tasks.
              </li>
              <li>
                Review, edit if needed, and confirm. Only then (unless Skip
                Approve is on) does Vocify write to HubSpot.
              </li>
              <li>
                Open the contact, company, or deal timeline in HubSpot. You
                should see the note, any new or updated properties, follow-up
                tasks, and — for dialer calls — the Call activity with
                recording when it is ready.
              </li>
            </ol>

            <h3 className="text-lg font-bold text-foreground pt-2">
              WhatsApp (field)
            </h3>
            <ol className="list-decimal pl-6 space-y-3">
              <li>
                Add your WhatsApp number on{" "}
                <a href={PROFILE} className="text-beige font-semibold hover:underline">
                  Profile
                </a>{" "}
                in international format.
              </li>
              <li>
                Send a voice note to the Vocify WhatsApp number your workspace
                was given at onboarding.
              </li>
              <li>
                Vocify processes the note the same way as a dashboard memo and
                writes to HubSpot under your connected account.
              </li>
            </ol>

            <h3 className="text-lg font-bold text-foreground pt-2">
              Chrome side panel and dialer
            </h3>
            <p>
              The Chrome extension is optional. The HubSpot integration works
              from the dashboard and WhatsApp without it. If your team uses the
              side panel, open it on a HubSpot contact or deal, record a memo
              or place a Pro dialer call, then review proposed changes the same
              way. The dialer logs a Call on that record, sets the call
              outcome, and attaches the recording when HubSpot can fetch it.
            </p>

            <h3 className="text-lg font-bold text-foreground pt-2">
              Automated vs manual
            </h3>
            <ul className="list-disc pl-6 space-y-2">
              <li>
                <strong className="text-foreground">Manual:</strong> you record,
                review proposed changes, and confirm.
              </li>
              <li>
                <strong className="text-foreground">Automated:</strong> with
                Skip Approve on, a finished call or locked memo writes the
                allowed fields, note, and tasks without a person sitting on
                Approve. You can open the memo afterwards to correct mistakes.
              </li>
            </ul>
          </Section>

          <Section id="shared-data" title="Shared data">
            <p>
              Every object below is a scope Vocify requests at install. If we
              request read and write, the listing treats that object as
              bidirectional.
            </p>
            <div className="overflow-x-auto rounded-2xl border border-border/70">
              <table className="w-full text-sm text-left">
                <thead className="bg-secondary/10 text-foreground">
                  <tr>
                    <th className="px-4 py-3 font-semibold">HubSpot object</th>
                    <th className="px-4 py-3 font-semibold">Direction</th>
                    <th className="px-4 py-3 font-semibold">What moves</th>
                  </tr>
                </thead>
                <tbody>
                  {SCOPE_ROWS.map((row) => (
                    <tr key={row.object} className="border-t border-border/50">
                      <td className="px-4 py-3 text-foreground font-medium">
                        {row.object}
                      </td>
                      <td className="px-4 py-3">{row.direction}</td>
                      <td className="px-4 py-3">{row.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              After a memo or dialer call, Vocify can also create HubSpot{" "}
              <strong className="text-foreground">tasks</strong> and{" "}
              <strong className="text-foreground">Call</strong> engagements
              (body, outcome, duration, recording). Those writes use the
              connected app; they are not extra OAuth objects on the install
              screen.
            </p>
            <p>
              Vocify does not sell CRM data. Audio is transcribed to produce
              the update. See the{" "}
              <Link to="/privacy" className="text-beige font-semibold hover:underline">
                Privacy Policy
              </Link>
              .
            </p>
          </Section>

          <Section id="pricing" title="Pricing">
            <p>
              Both plans include the HubSpot integration. Prices are in euros,
              billed per workspace seat.
            </p>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="rounded-2xl border border-border/70 bg-card p-6">
                <p className="text-[13px] text-muted-foreground">Starter</p>
                <p className="text-2xl text-foreground mt-1">€39 / month</p>
                <p className="text-sm mt-1">or €390 / year (€33 / month)</p>
                <p className="mt-4">
                  Voice memos, transcription, HubSpot field updates, notes,
                  tasks, and follow-ups. No Vocify dialer.
                </p>
              </div>
              <div className="rounded-2xl border border-border/70 bg-card p-6">
                <p className="text-[13px] text-muted-foreground">Pro</p>
                <p className="text-2xl text-foreground mt-1">€59 / month</p>
                <p className="text-sm mt-1">or €590 / year (€49 / month)</p>
                <p className="mt-4">
                  Everything in Starter, plus the Vocify dialer with 1,000
                  minutes included so calls land on the HubSpot timeline with
                  recording.
                </p>
              </div>
            </div>
            <p>
              Subscribe in{" "}
              <a href={SETTINGS_BILLING} className="text-beige font-semibold hover:underline">
                Settings → Billing
              </a>
              . Book a walkthrough at{" "}
              <a
                href="https://meetings-eu1.hubspot.com/dani-zal?uuid=e04c2511-8c6b-424b-8dd9-b5eddfe1e87c"
                className="text-beige font-semibold hover:underline"
              >
                getvocify.com
              </a>{" "}
              if you need onboarding help.
            </p>
          </Section>

          <Section id="disconnect" title="Disconnect HubSpot from Vocify">
            <p>
              Disconnecting stops all future writes from Vocify to that HubSpot
              account. Contacts, companies, deals, tasks, notes, and Calls
              already in HubSpot stay where they are. Vocify deletes the
              connection, saved field mapping, and sync history for that CRM.
            </p>
            <ol className="list-decimal pl-6 space-y-3">
              <li>
                Sign in as a workspace owner or admin.
              </li>
              <li>
                Open{" "}
                <a href={SETTINGS_CRM} className="text-beige font-semibold hover:underline">
                  Settings → CRM
                </a>
                .
              </li>
              <li>
                On the HubSpot row, click the disconnect control.
              </li>
              <li>
                Confirm <strong className="text-foreground">Disconnect</strong>.
              </li>
            </ol>
          </Section>

          <Section id="uninstall" title="Uninstall Vocify from a HubSpot account">
            <p>
              Uninstalling inside HubSpot revokes OAuth. Vocify can no longer
              call the HubSpot APIs for that portal. Existing HubSpot records
              are not deleted. If the Vocify workspace still shows Connected,
              disconnect there too so field mapping is cleared.
            </p>
            <ol className="list-decimal pl-6 space-y-3">
              <li>
                In HubSpot, open Settings → Integrations → Connected Apps.
              </li>
              <li>
                Find Vocify, click Actions, then Uninstall.
              </li>
              <li>
                Type <strong className="text-foreground">uninstall</strong> and
                confirm.
              </li>
            </ol>
            <p>
              HubSpot&apos;s own steps:{" "}
              <a
                href={UNINSTALL_KB}
                className="text-beige font-semibold hover:underline"
                rel="noopener noreferrer"
              >
                install and uninstall Marketplace apps
              </a>
              .
            </p>
          </Section>

          <section className="pt-8 border-t border-border/50 space-y-4">
            <h2 className="text-2xl font-bold tracking-tight">Need help?</h2>
            <p>
              Email{" "}
              <a
                href="mailto:support@getvocify.com"
                className="text-beige font-semibold hover:underline"
              >
                support@getvocify.com
              </a>{" "}
              (reply within two business hours, Monday–Friday) or open{" "}
              <Link to="/support" className="text-beige font-semibold hover:underline">
                Support
              </Link>
              .
            </p>
          </section>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default DocsPage;
