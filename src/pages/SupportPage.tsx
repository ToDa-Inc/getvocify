import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";

const SupportPage = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-24">
        <h1 className="text-4xl font-black mb-4 tracking-tight">Support</h1>
        <p className="text-muted-foreground mb-12">
          Need help with Vocify or your HubSpot connection? We're here for you.
        </p>

        <div className="prose prose-slate max-w-none space-y-12">
          <section>
            <h2 className="text-2xl font-bold mb-4">Contact us</h2>
            <p className="text-lg leading-relaxed text-muted-foreground">
              Email us at{" "}
              <a href="mailto:support@getvocify.com" className="text-beige font-semibold hover:underline">
                support@getvocify.com
              </a>{" "}
              and we'll get back to you within 2 business hours (Mon–Fri).
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">Common questions</h2>
            <div className="space-y-6">
              <div>
                <h3 className="font-bold text-foreground mb-1">¿Cómo conecto Vocify con HubSpot?</h3>
                <p className="text-muted-foreground">
                  Desde el panel de Vocify, ve a Integraciones → HubSpot → Conectar HubSpot, e inicia sesión con tu
                  cuenta. Consulta la{" "}
                  <a href="/docs" className="text-beige font-semibold hover:underline">
                    guía de configuración
                  </a>{" "}
                  para más detalles.
                </p>
              </div>
              <div>
                <h3 className="font-bold text-foreground mb-1">¿Qué datos de HubSpot usa Vocify?</h3>
                <p className="text-muted-foreground">
                  Vocify lee y actualiza contactos, empresas y negocios en tu cuenta de HubSpot, únicamente para
                  reflejar la información extraída de tus memos de voz. Nunca compartimos ni vendemos tus datos.
                </p>
              </div>
              <div>
                <h3 className="font-bold text-foreground mb-1">¿Cómo desconecto la integración?</h3>
                <p className="text-muted-foreground">
                  Ve a Integraciones → HubSpot → Desconectar. También puedes revocar el acceso desde Settings →
                  Integrations → Connected apps en tu cuenta de HubSpot.
                </p>
              </div>
            </div>
          </section>

          <section className="pt-12 border-t">
            <h2 className="text-2xl font-bold mb-4">Report a security issue</h2>
            <p className="text-muted-foreground">
              If you believe you've found a security vulnerability, please email{" "}
              <a href="mailto:support@getvocify.com" className="text-beige font-semibold hover:underline">
                support@getvocify.com
              </a>{" "}
              directly rather than filing a public issue.
            </p>
          </section>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default SupportPage;
