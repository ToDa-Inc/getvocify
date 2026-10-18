# Proceso de venta editable: tipos de interacción propios, playbook desde cero y tipos por miembro

Fecha: 2026-10-17
Estado: aprobado por Toni en el chat ("sí, ejecútalo todo"). Se construye apagado tras el flag `SALES_PROCESS_ENABLED`.

## 1. Objetivo

Hoy una empresa elige entre un catálogo fijo de tipos (Llamada en frío, Lead inbound, Discovery, Demo y cierre…),
agrupados en Llamadas y Reuniones, y a cada miembro se le da un rol SDR / AE / General. Queremos lo contrario:

1. La empresa **define su proceso de venta**: una lista ordenada de tipos de interacción con sus propios nombres
   (Llamada en frío, Discovery, Demo…). Editable siempre.
2. **Después** define qué pasa en cada tipo. Si no tiene playbook, Vocify lo construye con ella desde cero, con
   preguntas; las plantillas solo son ayuda dentro de esas preguntas.
3. Los roles son **owner / admin / miembro**. Owner y admin gestionan; a cada miembro se le asignan los tipos que
   ejecuta (uno, varios o todos), al invitarle o desde su perfil.
4. El rol SDR/AE/General deja de ser algo que se elige. No cambia lo que ve ni lo que recibe ningún usuario actual.

## 2. Qué existe ya y se reutiliza

- Los tipos ya son filas por empresa (`playbooks`: `sales_motion_key`, `label`, `applies_to`, `recognize`, estado) y
  se pueden crear con `add_type` / `set_meta`. El lector de llamadas ya elige el tipo entre los publicados de la
  empresa, con su frase `recognize`.
- `company_members.sales_role` y `company_invitations.sales_role` (`sdr|ae|general|NULL`) alimentan unos 50
  ficheros: coaching, informes, traspasos SDR→AE, permisos del CRM, Hoy, Ask.

## 3. Decisiones

1. **Cada tipo lleva dos datos nuevos:** `position` (orden en el proceso) y `stage`: `first_contact` (busca
   conseguir una reunión) o `deal` (hace avanzar o cerrar la venta). `stage` es lo que hoy dicen el rol y el
   objetivo de un tipo del catálogo, y el usuario lo elige en lenguaje llano. Los tipos del catálogo ya creados
   lo reciben de su rol: `sdr` → `first_contact`, `ae` → `deal`.
2. **Cada miembro (y cada invitación) lleva `interaction_types`:** lista de claves de tipo, `NULL` = todos.
3. **El rol de ventas se deriva, no se elige.** Al guardar `interaction_types` se escribe `sales_role` con una
   función pura: solo tipos `first_contact` → `sdr`; solo `deal` → `ae`; mezcla o `NULL` → `general`. Así las ~50
   lecturas siguen igual y un SDR de hoy sigue siendo SDR. Más adelante cada sitio puede leer los tipos directamente.
4. **Migración de lo existente:** `interaction_types` se rellena a partir del rol (sdr → sus tipos `first_contact`,
   ae → los `deal`, general/NULL → `NULL`). `position` sigue el orden del catálogo. Sin cambios visibles.
5. **Quién ve qué tipo y a qué tipo va una llamada:** si el miembro tiene tipos asignados, solo ve esos y el
   enrutado y el lector de llamadas solo eligen entre ellos; con un único tipo, la llamada va a ese. Sin tipos
   asignados rige lo de hoy.
6. **Los canales Llamadas / Reuniones dejan de estructurar la pantalla.** El proceso es una sola lista. El canal
   sigue existiendo como dato de la llamada y como condición opcional de una regla avanzada.
7. **La definición de un tipo propio** (nombre + "qué buscas conseguir" + frase de cómo reconocerlo) es lo que lee el
   lector de llamadas (`describe_type`), en lugar de "un tipo definido por la empresa".
8. **Flag nuevo `SALES_PROCESS_ENABLED`** (apagado por defecto, expuesto al cliente). Con él apagado nada cambia: ni
   pantalla, ni API, ni enrutado.

## 4. Pantallas

- **Tu proceso de venta** (primera vez y siempre editable): lista ordenada de tipos; cada fila con nombre, "qué
  buscas conseguir" (dos opciones) y una frase opcional de cómo reconocerlo; añadir, renombrar, reordenar, quitar.
  Un empresa sin proceso empieza con una sola pregunta: "¿Qué tipos de interacción tenéis?", y puede partir de una
  sugerencia (por ejemplo Llamada en frío → Discovery → Demo → Cierre) que edita libremente.
- **Construir cada tipo con Vocify:** el asistente de preguntas guiadas (ya existente) pasa a preguntar, tipo a tipo,
  qué pasa dentro (pasos, qué dice, objeciones habituales); las plantillas aportan las preguntas y los ejemplos, no el
  contenido. Subir un playbook entero, por partes o por voz sigue repartiéndose entre los tipos de la empresa.
- **Equipo:** al invitar y en el perfil de un miembro, "Qué interacciones hace" con casillas de los tipos (todas
  por defecto). Desaparece el selector SDR/AE/General. Los roles visibles son Owner, Admin y Miembro.

## 5. Fuera de alcance

- Reescribir los ~50 sitios que leen `sales_role` para que lean los tipos (se hace después, sin urgencia).
- Subir una llamada modelo en la misma caja del playbook (pendiente de decidir con Toni).
- Cambiar cómo puntúa coaching o qué incluyen los informes.

## 6. Riesgos y comprobaciones

- Una empresa que ya usa el catálogo no debe notar nada: test de que, con `interaction_types` a `NULL` y el flag
  apagado, `route`, `visible_to_role` y el lector de llamadas devuelven lo mismo que antes.
- La función rol-desde-tipos es pura y se prueba con todas las combinaciones, incluida la lista vacía y claves que ya
  no existen.
- Migración idempotente (`IF NOT EXISTS`, columnas que admiten vacío) y SQL de activación para el fundador.
- Borrar un tipo asignado a un miembro: se quita de su lista; si queda vacía vuelve a `NULL` (todos).

## 7. Pantalla de Playbook (18 oct 2026)

Con `SALES_PROCESS_ENABLED` la página Playbook es una sola pantalla sobre el fondo de la app, con tres bloques; sin el flag
es la de siempre. Plan: `docs/superpowers/plans/2026-10-18-playbook-funnel-y-empresa.md`.

- **Funnel de ventas** (izquierda): las interacciones de la empresa dibujadas de más ancha a más estrecha; bajo cada una, su
  objetivo; un clic abre su panel de siempre (pasos, objeciones, publicar) en una ventana lateral. Vacío: croquis con «Crear +».
- **Vuestra empresa** (derecha): empresa, producto, oferta, competencia, ICP y casos, cada una con su estado; un clic abre la
  ventana de la empresa. El texto de «Producto y oferta», que vivía en Ajustes, está arriba en esa ventana (mismo dato,
  `companies.product_context`); la entrada de Ajustes desaparece y su URL lleva a Playbook.
- **Otro tipo de llamadas** (abajo): llamadas fuera del funnel (soporte, una llamada técnica) con `stage = other`: no puntúan en
  coaching, no exigen objetivo ni descripción y pueden tener pasos o solo información.
- **Crear** abre una ventana: nombre y objetivo de la llamada (el objetivo, imprescindible en las del funnel). La descripción ya no
  se pide (18 oct): Vocify reconoce el tipo por su nombre y objetivo; una `recognize` ya escrita se conserva. La fase sale del orden. La primera vez ofrece tres caminos: un PDF completo,
  un documento por interacción, o responder preguntas y crearlo con Vocify.
- Migración 085: `company_sales_process.goal` y `stage` admite `other`.
- Pendiente: avisar al jefe cuando una pregunta técnica se repite sin respuesta (hoy lo cubre el asistente de «Lo que falta»).

