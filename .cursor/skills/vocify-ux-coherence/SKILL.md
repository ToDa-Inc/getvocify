---
name: vocify-ux-coherence
description: Principios obligatorios de UX/UI y coherencia de producto para el repo de Vocify. Aplícala siempre que planifiques o implementes cualquier feature, pantalla, componente, flujo, email o texto generado por IA en dashboard, extensión o app desktop. Úsala al crear planes, no solo al escribir código.
---

# Vocify: coherencia de producto y UX

## Principio rector

Con menos información, más valor. Menos clics, más resultado. La UI tiene
claridad directa y todas las superficies (dashboard, extensión, desktop) se
sienten un solo producto. La referencia de fluidez y calidad de interacción
es Granola: suave, silenciosa, sin fricción.

Una feature no está terminada si funciona pero desentona, añade clics
innecesarios o deja a la UI en un estado incoherente con el resto.

## 1. Antes de proponer o tocar nada

- Analiza lo que ya existe en las superficies afectadas: componentes,
patrones, tokens de estilo, layout, copy, flujos actuales. Cita los
archivos concretos.
- Reutiliza patrones y componentes existentes. Crea uno nuevo solo si
ninguno sirve, y justifícalo.
- Sigue el styling del repo. No introduzcas estilos, espaciados, colores ni
convenciones nuevas sin motivo explícito.
- Relee los criterios que el usuario ya dejó en docs y planes (p. ej. el
"Definition of Done" y la sección de "sin AI slop"). No los redescubras
ni los omitas: aplícalos.



## 2. Todo el plan debe incluir explícitamente

- **Análisis de estado actual** de dashboard, extensión y desktop en lo que
afecte a la feature.
- **Diseño de UI**: cómo se ve, qué se prioriza, qué información se muestra
y cuál se oculta. Cómo se concatena con el resto de pantallas.
- **Integración entre superficies**: qué hace cada una (dashboard,
extensión, desktop) y cómo se conectan. No omitas ninguna que sea
relevante (p. ej. la extensión a nivel de contacto para preparar
llamadas).
- **Plan técnico concreto**: qué archivos y módulos se tocan, por qué y cómo
encaja con la arquitectura existente.
- **Edge cases y su solución**, en cada ámbito de la feature. Incluye
siempre el estado vacío ("todavía no hay nada") con un diseño útil que
permita construir a partir de ahí.
- **Entrega completa** cuando aplique: instalador/DMG, descarga para Mac,
logo, etc. La feature va de punta a punta, no a medias.



## 3. Reglas de UX

- Menos clics: si un paso se puede inferir, se infiere.
- Muestra lo esencial primero; el detalle, bajo demanda.
- Transiciones suaves, sin saltos, parpadeos ni reordenaciones bruscas.
- Datos en streaming (p. ej. transcripción en chunks de 1-2 palabras): se
presentan ya unidos y legibles, nunca fragmentados. Comprueba también el
estado final tras terminar de grabar.
- Cada pantalla tiene un foco claro y una acción principal evidente.
- Estados vacíos, de carga y de error siempre diseñados, nunca por defecto.



## 4. Sin AI slop

Todo texto generado por IA que vea el usuario (tareas, sugerencias, briefs,
tarjetas, emails) debe ser corto, directo y específico al contexto.

- Nada genérico, nada de relleno, nada de tono "asistente".
- Los emails deben sonar escritos por una persona con criterio, con buen
estilo. El modelo usado para generarlos debe ser bueno, y el prompt
debe forzar especificidad.
- Esto es criterio de aceptación, no de estilo: entra en el Definition of
Done de cada feature que genere texto.



## 5. Checklist antes de dar algo por hecho

- [ ] ¿Reutiliza patrones y estilos existentes?
- [ ] ¿Encaja visual y funcionalmente con las otras superficies?
- [ ] ¿Menos clics y menos información para el mismo valor?
- [ ] ¿Edge cases y estado vacío cubiertos y diseñados?
- [ ] ¿Textos de IA cortos, directos y sin slop?
- [ ] ¿Está claro qué archivos se tocan y por qué?



## 6. Proporcionalidad (peso visual acorde a la importancia)

- El peso visual de un elemento debe ser proporcional a su frecuencia de
uso y a su importancia. Acción principal = protagonista. Todo lo demás
= enlace, icono o control compacto.
- Ajustes puntuales (idioma, opciones de login alternativas, preferencias)
no ocupan espacio principal: van en ajustes, footer o enlace secundario.
- Máximo una línea de texto de apoyo, o ninguna. Si una función necesita
un párrafo para entenderse, rediseña el flujo.
- Antes de añadir UI, prueba primero soluciones sin UI: detección
automática, valores por defecto inteligentes, inferir del contexto.
- En superficies pequeñas (popup de extensión), respeta el espacio: una
feature secundaria no puede quitar espacio a la acción principal.
- Reutiliza las variantes existentes del componente (ghost, link, icon)
en lugar de crear botones nuevos.
- En el plan, para cada elemento nuevo indica: dónde va, qué peso visual
tiene y por qué. Con captura o descripción, antes de implementar.

  
## 7. Pensar el recorrido

Antes de diseñar, sitúa la feature dentro del recorrido real de la persona.

No lo inventes: si el repo o los docs ya lo describen, úsalo; si no, declara

tus suposiciones para que se puedan corregir.

**Preguntas que guían el diseño**

- ¿Qué está intentando lograr la persona, y qué acaba de hacer antes de

  llegar aquí? ¿Qué hará justo después?

- ¿En qué estado está: con prisa, con la cabeza en otra cosa, concentrada?

  La UI se dimensiona a la atención disponible en ese momento.

- ¿Qué le cuesta más si falla: tiempo, confianza o algo que va a usar de

  cara a otros? Ahí el listón es impecable. En el resto basta con que sea

  coherente y discreto.

- ¿Qué información necesita realmente en este punto, y cuál puede esperar?

- ¿Dónde espera encontrar esto? Lo hecho en una superficie debe aparecer

  donde lo buscaría en las otras, sin repetir pasos ni datos.

**Edge cases: derívalos del recorrido, no del código**

Recorre el flujo preguntando qué pasa cuando:

- no hay nada todavía (primera vez, o cuenta vacía)

- hay datos a medias o de mala calidad

- algo se interrumpe (cierre, red, cambio de contexto)

- hay mucho más volumen del esperado

- algo falla y hay que volver al flujo sin perder lo hecho

Para cada uno, define qué ve la persona y cómo sigue sin bloquearse. Si un

caso no aplica, no lo rellenes.

**En el plan**

Incluye un recorrido breve: los pasos, los momentos críticos marcados y qué

se prioriza en cada uno.