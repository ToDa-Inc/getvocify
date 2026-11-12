import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";
import { useLanguage } from "@/lib/i18n";

type Item = { label?: string; text: string };
type Section = { title: string; paragraphs?: string[]; items?: Item[] };
type Policy = { title: string; updated: string; sections: Section[] };

const COMPANY =
  "ZARK GROWTH LIMITED, Hong Kong, nº 78846325 — Unit B6, 12th Floor, Wing Wah Building, No. 677 King's Road, Quarry Bay, Hong Kong";
const EMAIL = "toni@getvocify.com";

const ES: Policy = {
  title: "Política de privacidad",
  updated: "Última actualización: 12 de noviembre de 2026",
  sections: [
    {
      title: "1. Quiénes somos",
      paragraphs: [
        `Vocify es una plataforma de ZARK GROWTH LIMITED, sociedad titular y responsable de Vocify (${COMPANY}).`,
        `Representante en la Unión Europea (artículo 27 del RGPD): Toni Mora Botella, Países Bajos. Contacto para protección de datos: ${EMAIL}.`,
      ],
    },
    {
      title: "2. Nuestro papel",
      items: [
        {
          label: "Encargado del tratamiento",
          text: "Las llamadas, reuniones, visitas, notas de voz, transcripciones y datos del CRM que tu empresa trata con Vocify son de tu empresa, que es la responsable. Vocify los trata solo siguiendo sus instrucciones, según el contrato de encargo del tratamiento firmado con ella. Para ejercer tus derechos sobre esos datos, dirígete a tu empresa; te ayudaremos si nos lo pide.",
        },
        {
          label: "Responsable del tratamiento",
          text: "Vocify es responsable de los datos de las cuentas de usuario, del soporte, de los emails de notificación y de la facturación.",
        },
      ],
    },
    {
      title: "3. Datos que tratamos",
      items: [
        { label: "Cuenta", text: "Nombre, email, empresa, rol y tokens de acceso cifrados para mantener tu sesión y tus integraciones." },
        { label: "Audio", text: "Solo cuando grabas una llamada, reunión, visita o nota de voz. El audio se usa únicamente para transcribirlo." },
        { label: "Transcripciones y análisis", text: "El texto de las conversaciones y lo que Vocify genera a partir de él: resúmenes, compromisos, objeciones, sugerencias durante la llamada y coaching." },
        { label: "CRM y calendario", text: "Los datos de contactos, empresas, negocios y reuniones de las herramientas que conectas (por ejemplo HubSpot, Pipedrive, Salesforce, Google o Microsoft)." },
        { label: "Muestra de voz (opcional)", text: "Si la activas, una representación de tu voz para distinguirte de la otra persona en la llamada. Puedes borrarla cuando quieras; el audio de la muestra no se guarda." },
        { label: "Extensión de Chrome", text: "La URL de la pestaña activa, solo mientras grabas, para asociar la grabación al registro correcto del CRM." },
        { label: "Facturación", text: "Datos de la empresa y de la persona de contacto de facturación. Los datos de la tarjeta los trata directamente el proveedor de pagos." },
      ],
    },
    {
      title: "4. Para qué y con qué base",
      items: [
        { text: "Prestar el servicio que tu empresa ha contratado: grabar, transcribir, analizar y registrar en el CRM (por cuenta de tu empresa)." },
        { text: "Gestionar tu cuenta, darte acceso, enviarte las notificaciones del servicio y atender soporte (ejecución del contrato e interés legítimo en la seguridad del servicio)." },
        { text: "Facturar (ejecución del contrato y obligaciones legales contables y fiscales)." },
        { text: "No vendemos, alquilamos ni cedemos datos personales a terceros, y no los usamos para publicidad." },
      ],
    },
    {
      title: "5. Dónde están los datos y quién los trata",
      paragraphs: [
        "Los datos se alojan en servidores de la Unión Europea. Estos proveedores los tratan por cuenta de Vocify, con contrato de encargo del tratamiento firmado o aceptado:",
      ],
      items: [
        { label: "Railway", text: "Servidores de la aplicación. UE (Países Bajos)." },
        { label: "Supabase", text: "Base de datos, autenticación y archivos. UE." },
        { label: "OpenRouter / Microsoft Azure", text: "Transcripción de audio. UE (Suecia)." },
        { label: "Vercel", text: "Transcripción de respaldo, solo cuando la principal falla. EE. UU." },
        { label: "Together AI", text: "Análisis con IA del texto de las transcripciones. EE. UU." },
        { label: "Resend", text: "Emails de notificación de Vocify. EE. UU." },
        { label: "Twilio", text: "Telefonía, solo si llamas desde Vocify. EE. UU." },
        { label: "Stripe", text: "Pagos y facturación." },
      ],
    },
    {
      title: "6. Transferencias fuera de la UE",
      paragraphs: [
        "Cuando un proveedor trata datos fuera del Espacio Económico Europeo, la transferencia se ampara en el Marco de Privacidad de Datos UE-EE. UU. (para los proveedores certificados) o en las cláusulas contractuales tipo de la Comisión Europea.",
      ],
    },
    {
      title: "7. Datos de Google",
      paragraphs: [
        "El uso que Vocify hace de la información recibida de las API de Google se ajusta a la Política de datos de usuario de los servicios de API de Google y a la Política de datos de usuario de Chrome Web Store, incluidos los requisitos de uso limitado (Limited Use).",
      ],
    },
    {
      title: "8. Cuánto tiempo los guardamos",
      items: [
        { text: "Datos del servicio: mientras tu empresa tenga contratado Vocify. Al terminar, se borran o se devuelven en 30 días, como elija tu empresa." },
        { text: "Cuenta: mientras esté activa y, después, durante los plazos de prescripción de las responsabilidades del contrato." },
        { text: "Facturación: durante los plazos legales de la documentación contable y fiscal." },
      ],
    },
    {
      title: "9. Seguridad",
      paragraphs: [
        "Todas las comunicaciones van cifradas (HTTPS/WSS). La base de datos está cifrada en reposo, los datos de cada empresa están separados y el acceso se controla por roles. Los tokens de los CRM se guardan cifrados y el acceso de nuestro equipo es limitado y sujeto a confidencialidad. Si hay una brecha de seguridad, avisamos a la empresa afectada en un máximo de 48 horas.",
      ],
    },
    {
      title: "10. Tus derechos",
      paragraphs: [
        `Puedes pedir el acceso, la rectificación, la supresión, la oposición, la limitación y la portabilidad de tus datos. Para los datos de tu cuenta, escríbenos a ${EMAIL}. Para los datos que tu empresa trata con Vocify, dirígete a tu empresa.`,
        "También puedes reclamar ante la autoridad de protección de datos de tu país; en España, la Agencia Española de Protección de Datos (aepd.es).",
      ],
    },
    {
      title: "11. Cambios",
      paragraphs: [
        "Si cambiamos esta política, actualizaremos la fecha de arriba. Avisaremos a las empresas cliente de cualquier nuevo proveedor con al menos 15 días de antelación.",
      ],
    },
  ],
};

const EN: Policy = {
  title: "Privacy Policy",
  updated: "Last updated: 12 November 2026",
  sections: [
    {
      title: "1. Who we are",
      paragraphs: [
        `Vocify is a platform of ZARK GROWTH LIMITED, the company that owns and is responsible for Vocify (${COMPANY}).`,
        `Representative in the European Union (Article 27 GDPR): Toni Mora Botella, the Netherlands. Data protection contact: ${EMAIL}.`,
      ],
    },
    {
      title: "2. Our role",
      items: [
        {
          label: "Processor",
          text: "The calls, meetings, visits, voice notes, transcripts and CRM data your company handles with Vocify belong to your company, which is the controller. Vocify processes them only on its instructions, under the data processing agreement signed with it. To exercise your rights over that data, contact your company; we will help if it asks us to.",
        },
        {
          label: "Controller",
          text: "Vocify is the controller of user account data, support, notification emails and billing.",
        },
      ],
    },
    {
      title: "3. Data we process",
      items: [
        { label: "Account", text: "Name, email, company, role and encrypted access tokens to keep your session and integrations." },
        { label: "Audio", text: "Only when you record a call, meeting, visit or voice note. Audio is used only to transcribe it." },
        { label: "Transcripts and analysis", text: "The text of conversations and what Vocify generates from it: summaries, commitments, objections, live suggestions and coaching." },
        { label: "CRM and calendar", text: "Contact, company, deal and meeting data from the tools you connect (for example HubSpot, Pipedrive, Salesforce, Google or Microsoft)." },
        { label: "Voice sample (optional)", text: "If you turn it on, a representation of your voice to tell you apart from the other person on the call. You can delete it at any time; the sample audio is not kept." },
        { label: "Chrome extension", text: "The URL of the active tab, only while you record, to link the recording to the right CRM record." },
        { label: "Billing", text: "Company details and the billing contact. Card details are handled directly by the payment provider." },
      ],
    },
    {
      title: "4. Purposes and legal basis",
      items: [
        { text: "Providing the service your company signed up for: recording, transcribing, analysing and logging to the CRM (on your company's behalf)." },
        { text: "Managing your account, giving you access, sending service notifications and providing support (performance of the contract and legitimate interest in the security of the service)." },
        { text: "Billing (performance of the contract and legal accounting and tax obligations)." },
        { text: "We do not sell, rent or share personal data with third parties, and we do not use it for advertising." },
      ],
    },
    {
      title: "5. Where data is stored and who processes it",
      paragraphs: [
        "Data is hosted on servers in the European Union. These providers process it on Vocify's behalf, under a signed or accepted data processing agreement:",
      ],
      items: [
        { label: "Railway", text: "Application servers. EU (the Netherlands)." },
        { label: "Supabase", text: "Database, authentication and files. EU." },
        { label: "OpenRouter / Microsoft Azure", text: "Audio transcription. EU (Sweden)." },
        { label: "Vercel", text: "Backup transcription, only when the main one fails. US." },
        { label: "Together AI", text: "AI analysis of transcript text. US." },
        { label: "Resend", text: "Vocify notification emails. US." },
        { label: "Twilio", text: "Telephony, only if you call from Vocify. US." },
        { label: "Stripe", text: "Payments and billing." },
      ],
    },
    {
      title: "6. Transfers outside the EU",
      paragraphs: [
        "When a provider processes data outside the European Economic Area, the transfer relies on the EU-US Data Privacy Framework (for certified providers) or on the European Commission's standard contractual clauses.",
      ],
    },
    {
      title: "7. Google data",
      paragraphs: [
        "Vocify's use of information received from Google APIs adheres to the Google API Services User Data Policy and the Chrome Web Store User Data Policy, including the Limited Use requirements.",
      ],
    },
    {
      title: "8. How long we keep data",
      items: [
        { text: "Service data: while your company subscribes to Vocify. When it ends, it is deleted or returned within 30 days, as your company chooses." },
        { text: "Account: while it is active and, afterwards, for the limitation periods of contractual liabilities." },
        { text: "Billing: for the legal retention periods of accounting and tax records." },
      ],
    },
    {
      title: "9. Security",
      paragraphs: [
        "All communications are encrypted (HTTPS/WSS). The database is encrypted at rest, each company's data is kept separate and access is role based. CRM tokens are stored encrypted, and our team's access is limited and bound by confidentiality. If there is a security breach, we notify the affected company within 48 hours.",
      ],
    },
    {
      title: "10. Your rights",
      paragraphs: [
        `You can request access, rectification, erasure, objection, restriction and portability of your data. For your account data, email ${EMAIL}. For data your company processes with Vocify, contact your company.`,
        "You can also complain to the data protection authority in your country; in Spain, the Agencia Española de Protección de Datos (aepd.es).",
      ],
    },
    {
      title: "11. Changes",
      paragraphs: [
        "If we change this policy, we will update the date above. We notify client companies of any new provider at least 15 days in advance.",
      ],
    },
  ],
};

const PrivacyPage = () => {
  const { language } = useLanguage();
  const policy = language === "EN" ? EN : ES;

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-24">
        <h1 className="text-4xl font-black mb-4 tracking-tight">{policy.title}</h1>
        <p className="text-muted-foreground mb-12">{policy.updated}</p>

        <div className="prose prose-slate max-w-none space-y-12">
          {policy.sections.map((section) => (
            <section key={section.title}>
              <h2 className="text-2xl font-bold mb-4">{section.title}</h2>
              {section.paragraphs?.map((text) => (
                <p key={text} className="text-muted-foreground mb-4 leading-relaxed">
                  {text}
                </p>
              ))}
              {section.items && (
                <ul className="list-disc pl-6 space-y-3 text-muted-foreground">
                  {section.items.map((item) => (
                    <li key={item.text}>
                      {item.label && <strong className="text-foreground">{item.label}: </strong>}
                      {item.text}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default PrivacyPage;
