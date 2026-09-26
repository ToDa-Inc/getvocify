# Ideas y sinergias para más adelante (26 sep 2026)

**Estado:** para leer más adelante. No forma parte del plan de la Lista 2 ni se ejecuta nada de aquí sin decisión expresa.
**Origen:** repaso del PDF de features (19 sep) frente al código actual y lo decidido en las reuniones del 21 y 25 sep.

---

## 1. Lo que ya está hecho aunque se dejaba para una fase posterior

| Idea | Estado real |
|---|---|
| **Ask Vocify** (se dejaba para fase 2) | Hecho: lee los datos de Vocify y de Pipedrive, responde «¿a quién llamo hoy?» y enseña el botón de llamar. |
| **Chat del manager** | Ask con datos de equipo por rol. Devuelve las mismas métricas de adherencia que el panel. |
| **Evolución por comercial** | Adherencia semanal por comercial para el manager, sin ranking. Es la mayor parte de lo que se pedía, sin «skills» sueltos. |
| **Win/loss** | Equipo ya lee ganados y perdidos del CRM. Falta cruzarlo con las objeciones. |
| **Coaching en vivo** (se dejaba para fase 3) | La reunión del 21 lo pasó a V1 solo para reuniones. El motor existe (F12); falta el overlay del desktop (Dani). |

---

## 2. Cosas que podríamos hacer de una forma más fácil

### 2.1 Conectar Gmail y Outlook sin pasar la revisión de Google

El 21 sep se eligió la sincronización de email de HubSpot/Pipedrive porque la aprobación de Google parecía difícil. Datos verificados hoy:

| Opción | Qué permite | Aprobaciones | Plazo | Coste |
|---|---|---|---|---|
| `mailto:` (lo que hay hoy) | Abrir el cliente de correo del comercial | Ninguna | — | 0 |
| Enlace de redacción de Gmail u Outlook web | Abrir el borrador ya relleno directamente en Gmail u Outlook, eligiendo por el MX del dominio del comercial | Ninguna | Horas | 0 |
| **Unipile email** (hosted auth `*:EMAILS`) | Enviar desde Vocify, detectar respuestas, leer los emails enviados para aprender el estilo. Gmail, Outlook e IMAP. | **Ninguna nuestra**: usa el cliente OAuth de Unipile, ya verificado con CASA Tier 2 | 1–2 días de integración | Por cuenta conectada (confirmar tarifa) |
| Gmail API propia, solo envío (`gmail.send`, alcance «sensible») | Enviar | Verificación de marca y pantalla de consentimiento (sin auditoría CASA) | Días a semanas | 0 |
| Gmail API propia con lectura (`gmail.readonly`, alcance «restringido») | Leer y enviar | Verificación + **auditoría CASA Tier 2 anual** con un laboratorio | Semanas | Auditoría anual |
| Sincronización de HubSpot/Pipedrive (decisión del 21 sep) | Ver emails y respuestas en el CRM | Permiso `sales-email-read` y reconexión | Ya preparado (commit local) | 0 |

**Lo que daría Unipile** (ya es proveedor nuestro, para WhatsApp):
- **Envío con un clic** del follow-up desde Vocify, con constancia real de que se envió.
- **Aviso de «no te ha respondido»** para todos los clientes, no solo para HubSpot con el permiso nuevo. Incluye Pipedrive sin sincronización de email y CRMs propios.
- **Estilo desde el primer día:** los últimos emails que el comercial envió a contactos de su CRM sirven como ejemplos de voz, sin pedirle nada.

**A confirmar antes de decidir:**
- la tarifa por cuenta conectada;
- que la pantalla de consentimiento de Google enseña la marca Unipile (salvo que más adelante usemos nuestro propio cliente OAuth y pasemos la verificación);
- que el acuerdo de tratamiento de datos (DPA) con Unipile cubre el email.

Minimizar datos: solo emails con contactos del CRM del comercial, y guardar el cuerpo solo de sus propios emails enviados.

**Cómo encaja:** no sustituye la decisión del 21 sep, la completa. Quien tenga la sincronización de email del CRM sigue por ahí; Unipile cubre al resto y añade el envío, que el CRM no da por API.

### 2.2 Aircall y Ringover a través de HubSpot, sin integrarlos

Mario (25 sep) dijo que HubSpot + Aircall están muy instaurados y que cambiar de dialer genera fricción. Muchas de esas llamadas ya se registran en HubSpot con `hs_call_recording_url`, y nuestro webhook de HubSpot procesa **cualquier** llamada con grabación: con auto-sync, o con el botón Transcribir de la extensión.

- **Comprobación:** con un portal real que use Aircall o Ringover, ver si la grabación se descarga.
- **Si se descarga:** funciona ya, solo hay que documentarlo y activarlo por cliente.
- **Si pide autenticación de Aircall:** la integración directa con su API sería un plan aparte.

### 2.3 Brief previo a reunión sin integrar el calendario

El calendario se decidió para más adelante, pero Vocify ya conoce las reuniones que se agendaron en sus conversaciones (F14, con hora aceptada por el comercial).

- Hoy enseñaría «Reunión hoy 11:00 · Marina (Acme)» el día de la reunión, reutilizando la tarjeta que ya existe.
- Al desplegarla: el brief previo más «Falta del playbook: decisor, presupuesto», con los pasos que la nota F09 marca como no cumplidos.

Límites honestos:
- solo salen las reuniones captadas por Vocify;
- si se movió en el CRM no lo sabemos, así que la tarjeta dice «acordada el {fecha}»;
- una reunión solo con día sale sin hora.

### 2.4 Conversación de la semana, sin biblioteca de llamadas

La biblioteca de mejores llamadas se dejó para V2. Una versión mínima sale barata con lo que ya existe:
- En el informe semanal de equipo y en Equipo, una sola conversación: la de mayor nota F09 de la semana **que además tenga una objeción resuelta**, para que no gane el prospecto fácil.
- Con la cita del momento y un enlace a la conversación.
- Del equipo, sin ranking de comerciales.

Pregunta abierta: ¿la ve solo el manager o también los comerciales, como se habló en la reunión?

---

## 3. Pequeñas cosas que se podrían añadir

- **Métricas de resultado por cliente:**
  - campos del CRM rellenos antes y después de Vocify;
  - horas de admin ahorradas por comercial y semana;
  - días hasta la primera actualización automática del CRM.

  La adherencia ya se mide. Las otras salen de datos que ya guardamos y darían la cifra para los testimonios de cada beta. Las horas ahorradas tienen que ser una estimación con fórmula visible, nunca un número inventado.
- **Resumen de Hoy por WhatsApp a las 8:30:** encaja con el canal que ya usan los comerciales de campo. Riesgo: el envío proactivo por WhatsApp puede chocar con la política de Meta y de Unipile.

---

## 4. Lo que seguiría fuera

- Bot que entra en las reuniones.
- Grabación presencial completa en el móvil.
- Roleplay con IA.
- Forecast.
- Leaderboards (choca con la decisión de no hacer ranking de comerciales).
- Pricing (pendiente con Dani).
