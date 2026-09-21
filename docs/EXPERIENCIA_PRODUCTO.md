# La experiencia Vocify
### Cómo se siente usar esto, no cómo se construye

*Visión de producto, no spec técnico — complementa `docs/features/ESTRUCTURA_INTELIGENTE.md` (la arquitectura) y `PRODUCT_OVERVIEW.md`. Esto es el "qué se siente al abrirlo", escrito para poder enseñárselo a un diseñador tal cual.*

---

## La frase que decide cada pantalla

**Cada llamada hace mejor la siguiente.**

Si una pantalla, un botón o una notificación no ayuda a que la próxima llamada salga mejor, no es Vocify — es ruido. Ese es el único filtro que hace falta para decidir qué entra y qué no.

Y la regla de forma, tan importante como la de fondo: **por debajo, mucho poder. Por encima, un solo gesto.** Toda la inteligencia — scoring, patrones, señales — vive escondida hasta el momento exacto en que hace falta. El comercial nunca abre un "panel de analítica". Se encuentra la razón correcta, en el sitio correcto, sin haberla pedido.

---

## 1. El Dashboard — no es un CRM, es "Hoy"

Cuando abres Vocify no ves un funnel, ni un gráfico de barras, ni una tabla de deals. Ves una lista de tarjetas. Cada una es una llamada que tiene sentido hacer ahora, con el motivo ya escrito encima:

> **Marina Ortiz — Tenéis Solutions**
> Te dijo "llámame en dos semanas" — han pasado 12 días.
> *Objeción sin cerrar: precio. Así la resolvió Alex la semana pasada → [ver]*
> `[ Llamar ]` `[ Posponer ]`

No hay una columna de "prioridad" numérica, ni un score visible. El orden ya viene decidido — follow-ups prometidos primero, leads calientes que se enfrían después, el resto por detrás — y la explicación siempre va delante del ranking, nunca al revés. Si el comercial tiene que preguntarse "¿por qué esto está arriba?", la tarjeta está mal escrita.

Arriba del todo, sin ocupar protagonismo, una tira discreta con el pulso del día — *"4 llamadas hoy, 3 con el CRM ya limpio, 1 por revisar"* — no un dashboard, un vistazo. Y siempre visible, sin buscarlo: el botón de captura (grabar / nota de voz / WhatsApp), porque lo único que nunca puede tener fricción es empezar.

**Vacío bien resuelto:** cuando no hay nada urgente, el dashboard no está vacío — dice *"Nada urgente hoy. Buen momento para prospectar en frío."* — nunca un hueco en blanco que parece que algo se rompió.

---

## 2. El copilot — no es una pestaña que abres, es alguien que aparece cuando toca

No hay un botón de "Copilot" en el menú. Hay cuatro momentos, y en cada uno el copilot se presenta distinto porque la necesidad es distinta:

**Antes de la llamada** — un brief de 10 segundos, no un documento. Aparece solo, en el dialer o en la ficha de la tarjeta: qué se dijo la última vez, la objeción abierta, el next step pactado. Nunca hay que ir a buscarlo.

**Durante la llamada** — el overlay flotante, mínimo, del tamaño de una línea. Calla la mayor parte del tiempo. Solo habla cuando hay algo que de verdad merece la pena — una objeción conocida con una respuesta que ya funcionó en el equipo — y entonces dice exactamente eso, en un renglón, sin interrumpir el ritmo de la conversación. Nunca lee el tono ni el estado de ánimo: escucha lo que se dice, no cómo se dice.

**Después de la llamada** — la pantalla de revisión, que es donde vive el "botón fácil" (sección 5). Aquí el copilot ya hizo el trabajo antes de que llegues: resumen, campos de CRM, borrador de email, todo esperando.

**Cuando tú lo llamas** — el mismo asistente, ahora conversacional, en WhatsApp o en un panel de chat: *"¿qué pasó con mis últimos contactos de esta semana? ¿qué objeciones se repitieron?"* Es el mismo cerebro que arma el dashboard, solo que aquí respondes tú la pregunta en vez de que la lista te la responda a ti.

La regla de identidad: el copilot nunca es una herramienta que operas. Es alguien que ya hizo la parte aburrida antes de que llegaras.

---

## 3. Tareas con contexto, no checkboxes con un título

Una tarea de Vocify nunca dice solo *"Llamar a Marina"*. Eso es una tarea de cualquier CRM y no enseña nada. Dice por qué, con la cita exacta si hace falta, y se resuelve con un gesto, no con un formulario:

> ~~Llamar a Marina Ortiz~~ →
> **Marina pidió que la llamaras en dos semanas — tras dudar por el precio.** Han pasado 12 días. `[ Llamar ahora ]` `[ Reprogramar ]` `[ Ya no aplica ]`

No existe la tarea genérica de "seguimiento". Cada una nace de algo concreto que se dijo, y por eso puede explicarse en una frase. Si no se puede explicar en una frase, no se crea la tarea — se deja para que un humano decida.

---

## 4. Datos inteligentes — nunca en forma de tabla

No hay una pantalla de "Analítica de objeciones" con barras y porcentajes esperando a que alguien la abra por curiosidad. Los patrones — qué objeción, qué respuesta funcionó, con qué resultado — solo aparecen incrustados donde ya estás: en el brief antes de llamar, en la línea del overlay durante la llamada, en el motivo de la tarjeta de la tarea. Es la diferencia entre un informe que hay que ir a leer y una ventaja que ya está puesta delante tuyo cuando la necesitas.

Si algún día hace falta una vista agregada (para el manager, sección 5), se construye — pero como una consecuencia de estos datos, nunca como la interfaz principal que ve el comercial.

---

## 5. Coaching — corriges una llamada, aprende todo el equipo

**Para el manager:** no escucha 30 llamadas, escucha 3 — las que el sistema ya marcó como las que importan (una objeción sin resolver, un silencio raro, una señal de riesgo). Deja feedback sobre un momento exacto de la conversación, no una nota general. Y ese feedback no se queda archivado: se convierte en una regla, y la próxima vez que cualquier comercial del equipo se cruce con esa misma objeción, la respuesta que funcionó ya está en su brief antes de que empiece la llamada.

**Para el comercial:** nunca ve primero un número. Ve una frase concreta — *"En el minuto 4 no llegaste a responder la duda de precio — así lo resolvió Alex la semana pasada"* — con el clip exacto si quiere escucharlo. El score existe por debajo (para que el manager pueda comparar y priorizar), pero nunca es lo primero que se muestra. Un 7/10 no enseña nada; una frase concreta sí.

---

## 6. Copilot en vivo — reuniones y llamadas

Mismo principio que el overlay de llamada (sección 2), aplicado a reuniones por vídeo o presenciales desde el desktop: una pastilla flotante, casi siempre en silencio, que solo aparece cuando hay una objeción reconocible con una respuesta que ya demostró funcionar en el equipo. Nunca un asistente que comenta todo lo que pasa — eso deja de ser útil a los tres minutos y se convierte en ruido que el comercial acaba ignorando o cerrando.

---

## 7. El desktop app — al estilo Granola, con identidad propia

La secuencia ya existe y es la correcta — no hace falta reinventarla, hace falta pulirla hasta que se sienta inevitable:

1. **Login** — sin fricción, una vez.
2. **Permisos** — la parte que más fácil se rompe la confianza. Copy ya bien resuelto: *"Vocify no graba tu pantalla"* — porque macOS pide el permiso de "Screen Recording" para algo que en realidad es solo audio, y hay que desactivar esa alarma antes de que se dispare en la cabeza del usuario.
3. **Escuchando** — un pulso suave, un cronómetro, y el transcript en vivo en dos carriles (Tú / Ellos). Aquí es donde la calidad de diarización real importa más — en una reunión de grupo, "Ellos" tiene que dejar de ser una sola voz.
4. **Revisión** — el momento Granola. Nunca "generando resumen..." con una rueda girando: cuando llegas a esta pantalla, el resumen ya está. No se siente como "la IA hizo tu trabajo", se siente como "tus notas, ya en limpio" — la diferencia entre un asistente que te ayudó y un robot que hizo algo por ti. Editable en cada campo, con un botón para descartar lo que no aplica, nunca todo o nada.

La pastilla flotante durante la llamada (la que ya existe) se queda tal cual: mínima, con una línea de transcript y un botón de parar. No necesita más — el overlay de coaching en vivo (sección 6) es una capa aparte, no hay que fundirlos en el mismo elemento visual o se vuelve ruidoso.

---

## 8. El botón fácil — el follow-up, resuelto como lo resuelve Granola

Esto es lo más importante de toda la pantalla de revisión, y tiene que sentirse instantáneo, no generado.

En el momento en que el comercial llega a la pantalla de revisión — tras colgar, tras salir de la reunión — el borrador del email ya está ahí, escrito con el tono real de esa persona (no una plantilla genérica: pistas de cómo escribe él o ella normalmente), mencionando lo que de verdad se dijo en la llamada, no relleno genérico tipo "fue un placer hablar contigo hoy". Un único botón, sin menú de opciones, sin "elige una plantilla":

> **Seguimiento listo para Marina**
> *(el email ya escrito, editable con un toque)*
> `[ Enviar ]`   `[ Enviar por WhatsApp ]`   `[ Editar ]`

Nunca "Generar email" como primer paso — eso es pedirle al usuario que espere a que la IA trabaje. El email ya está generado cuando el comercial llega a la pantalla; lo único que queda es decidir si se envía tal cual, se edita, o se manda por WhatsApp en vez de email si así es como habla con ese cliente. Un botón, una decisión, cero fricción.

---

## 9. El idioma de todo el producto

Ninguna pantalla dice "IA" como argumento — como ya vimos en el research de competidores, nadie compra por eso, todos compran por el tiempo que recuperan. La voz del producto es la de un compañero que ya hizo la parte pesada, no la de un sistema anunciando sus capacidades:

| No | Sí |
|---|---|
| "Generando resumen con IA..." | *(directamente el resultado, ya listo)* |
| "Score de la llamada: 7/10" | "Te faltó cerrar la objeción de precio — así lo hizo Alex" |
| "Acción sugerida por el motor de IA" | "Marina pidió que la llamaras — hace 12 días" |
| "CRM Autofill" (como feature a promocionar) | *(simplemente ocurre — no se anuncia)* |
| "No se encontraron tareas" | "Nada urgente hoy. Buen momento para prospectar." |

Regla corta: si una frase suena a que la escribió un ingeniero describiendo lo que hizo el sistema, se reescribe hasta que suene a que la escribió un compañero de ventas contándote lo que necesitas saber.
