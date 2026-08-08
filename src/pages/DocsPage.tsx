import Header from "@/components/landing/Header";
import Footer from "@/components/landing/Footer";

const DocsPage = () => {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="max-w-4xl mx-auto px-6 py-24">
        <h1 className="text-4xl font-black mb-4 tracking-tight">Documentation</h1>
        <p className="text-muted-foreground mb-12">
          Everything you need to set up and use Vocify with your CRM.
        </p>

        <div className="prose prose-slate max-w-none space-y-12">
          <section>
            <h2 className="text-2xl font-bold mb-4">1. Connect your HubSpot account</h2>
            <ol className="list-decimal pl-6 space-y-3 text-muted-foreground">
              <li>Log in to Vocify and open <strong className="text-foreground">Integrations</strong> in the dashboard.</li>
              <li>Click <strong className="text-foreground">Connect HubSpot</strong>.</li>
              <li>Sign in to HubSpot and select the account you want to connect.</li>
              <li>
                Review the requested permissions (contacts, companies and deals — read and write) and click{" "}
                <strong className="text-foreground">Connect app</strong>.
              </li>
              <li>You'll be redirected back to Vocify with your HubSpot account connected.</li>
            </ol>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">2. Record your first voice memo</h2>
            <p className="text-muted-foreground mb-4">
              Habla 30 segundos describiendo tu llamada, visita o reunión — quién, cuánto, y qué sigue. Vocify
              transcribe la nota, extrae los campos relevantes (contacto, empresa, valor del trato, próximo paso) y te
              muestra una vista previa antes de escribir nada en tu CRM.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">3. Revisa y confirma la actualización</h2>
            <p className="text-muted-foreground">
              Antes de tocar tu CRM, revisas la extracción propuesta por la IA y confirmas los cambios. Solo entonces
              Vocify crea o actualiza el contacto, empresa y/o negocio correspondiente en HubSpot, y programa las
              tareas de seguimiento detectadas en la conversación.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">4. Datos que sincroniza Vocify con HubSpot</h2>
            <ul className="list-disc pl-6 space-y-3 text-muted-foreground">
              <li><strong className="text-foreground">Contactos:</strong> nombre, empresa asociada, notas de la conversación.</li>
              <li><strong className="text-foreground">Negocios (deals):</strong> importe, etapa del pipeline, próxima fecha/acción.</li>
              <li><strong className="text-foreground">Empresas:</strong> asociación con contactos y negocios detectados en el memo.</li>
              <li><strong className="text-foreground">Tareas:</strong> seguimientos y recordatorios extraídos de la conversación.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold mb-4">FAQ</h2>
            <div className="space-y-6">
              <div>
                <h3 className="font-bold text-foreground mb-1">¿Funciona con mi CRM?</h3>
                <p className="text-muted-foreground">
                  Sí. Soportamos HubSpot, Salesforce y Pipedrive hoy mismo. Próximamente más integraciones.
                </p>
              </div>
              <div>
                <h3 className="font-bold text-foreground mb-1">¿Qué tan precisa es la IA?</h3>
                <p className="text-muted-foreground">
                  85-90% de precisión de serie. Siempre revisas antes de actualizar el CRM.
                </p>
              </div>
              <div>
                <h3 className="font-bold text-foreground mb-1">¿Qué pasa si hablo español/francés/alemán?</h3>
                <p className="text-muted-foreground">
                  Vocify soporta 6 idiomas: inglés, español, francés, alemán, italiano y portugués.
                </p>
              </div>
              <div>
                <h3 className="font-bold text-foreground mb-1">¿Mis datos están seguros?</h3>
                <p className="text-muted-foreground">
                  Sí. Cumplimos con GDPR. Datos guardados en la UE. Encriptados en tránsito y en reposo.
                </p>
              </div>
              <div>
                <h3 className="font-bold text-foreground mb-1">¿Puedo editar antes de actualizar el CRM?</h3>
                <p className="text-muted-foreground">Absolutamente. Revisas y apruebas cada actualización.</p>
              </div>
            </div>
          </section>

          <section className="pt-12 border-t">
            <h2 className="text-2xl font-bold mb-4">Need more help?</h2>
            <p className="text-muted-foreground">
              Visit our{" "}
              <a href="/support" className="text-beige font-semibold hover:underline">
                support page
              </a>{" "}
              or email us at{" "}
              <a href="mailto:support@getvocify.com" className="text-beige font-semibold hover:underline">
                support@getvocify.com
              </a>
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
