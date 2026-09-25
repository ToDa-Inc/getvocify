# Decisiones cerradas — 22 sep 2026

Estas decisiones sustituyen las preguntas abiertas del mismo tema. No se vuelven a pedir.

## F01 — distribución

La firma con Apple Developer, la notarización y el enlace público de descarga quedan fuera. El DMG interno sin firmar es el artefacto de esta rama. No se pregunta otra vez por la cuenta de Apple.

## F0 — worker

`INTELLIGENCE_WORKER_PUBLISH` sigue apagado. El código del worker existe y se puede seguir sin encender el flag. No se pregunta si hay que encenderlo.

## F03 — preparación previa

Aprobada con formato mínimo. Sustituye las cuatro filas fijas.

Antes de llamar se muestra solo lo que existe, en la extensión al abrir un contacto de HubSpot, sin llamada activa. Dashboard y escritorio repiten el mismo texto, sin otra composición.

Líneas posibles, como máximo tres, y solo si hay un hecho:

- Última conversación, en una frase, con fecha.
- Un pendiente real.
- Una objeción abierta. La respuesta del playbook solo aparece en esa línea, si el playbook publicado la tiene.

Contacto sin conversación: «Sin conversación todavía.» Si el CRM tiene una tarea abierta de verdad, una línea más, marcada como CRM. No se inventa última llamada, objeción ni consejo.

Contacto hablado que no dejó nada (sin siguiente paso, sin dolor confirmado, sin objeción): «Última vez: {fecha}. No quedó nada pendiente.» Nada más.

Lectura a medias: «No se pudo cargar todo.» más las líneas que sí llegaron. Un fallo no se presenta como «sin conversación».

Carga: una línea. No se reservan cuatro huecos. Al cambiar de contacto no se muestra el anterior.

Sin modelo nuevo, sin tabla nueva, sin panel inyectado en HubSpot.

## F09 — las 20 conversaciones

No son datos de una empresa ni se meten en el producto. El playbook de cada empresa sigue siendo la rúbrica.

Son un examen de desarrollo: un modelo genera transcripciones de llamadas y de meetings, con fallos de transcripción, ambigüedad y manejo de objeciones. Se guardan como eval en `backend/evals/F09/`. El código de producción no las cita. Sirven para comprobar que una reunión fácil no gana a una objeción bien trabajada, que lo ambiguo sigue siendo desconocido y que un error de transcripción no se convierte en una cita que no está en el texto.

## Cómo se ejecuta

Grok 4.7 coordina. Composer 2.5 Fast escribe el código mecánico. La lógica de contrato la cierra el coordinador. Varias tareas que no comparten archivos pueden ir a la vez. Los commits agrupan una entrega, no una función. El orden de producto del maestro se mantiene. F03 ya no bloquea el resto.
