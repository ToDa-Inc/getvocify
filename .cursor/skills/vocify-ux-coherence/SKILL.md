---
name: vocify-ux-coherence
description: Principios obligatorios de UX/UI, densidad de información y coherencia de producto para Vocify. Aplícala siempre que planifiques o implementes cualquier feature, pantalla, componente, flujo, email o texto generado por IA en dashboard, extensión o app desktop. Úsala al crear planes, no solo al escribir código. Cubre botones, iconos, tooltips, tabs, paginación, multi-select, drag, scroll y copy sin hardcode.
---

# Vocify: coherencia de producto y UX

## Principio rector

Con menos información, más valor. Menos clics, más resultado. La UI tiene
claridad directa y todas las superficies (dashboard, extensión, desktop) se
sienten un solo producto. La referencia de fluidez y calidad de interacción
es Granola: suave, silenciosa, sin fricción.

**Densidad:** revelar la máxima información útil con la mínima superficie.
La arquitectura de la pantalla es el mensaje. Si hay que explicar un control
con un párrafo, el control está mal. Si hay que esconder lo esencial detrás
de un clic, el layout está mal. Función y composición van juntas: lo que
se puede hacer se ve; lo que no importa ahora no ocupa.

Una feature no está terminada si funciona pero desentona, añade clics
innecesarios, obliga a scroll inútil o deja la UI incoherente con el resto.

Lee también [composition.md](composition.md) antes de inventar un control
nuevo. Si el caso ya está resuelto ahí, úsalo.

## 1. Antes de proponer o tocar nada

- Analiza lo que ya existe en las superficies afectadas: componentes,
  patrones, tokens, layout, copy, flujos. Cita los archivos concretos.
- Reutiliza patrones y componentes existentes. Crea uno nuevo solo si
  ninguno sirve, y justifícalo.
- Sigue el styling del repo. No introduzcas estilos, espaciados, colores ni
  convenciones nuevas sin motivo explícito.
- Kit base (no reinventar): `Button` (`default` / `ghost` / `link` / `icon`),
  `IconAction` (icono + tooltip + pending), `Tabs`, `Tooltip`, `Pagination`,
  `Checkbox`, `ScrollArea`, `DropdownMenu`, `Sheet`. Tokens en
  `THEME_TOKENS`. Listas: `PAGINATION.DEFAULT_PAGE_SIZE` (20).
- Relee los criterios que el usuario ya dejó en docs y planes (Definition
  of Done, "sin AI slop"). No los redescubras ni los omitas: aplícalos.

## 2. Todo el plan debe incluir explícitamente

- **Análisis de estado actual** de dashboard, extensión y desktop en lo que
  afecte a la feature.
- **Diseño de UI**: qué se ve, qué se prioriza, qué se oculta y cómo se
  concatena con el resto. Para cada control nuevo: dónde va, peso visual,
  y **por qué ese control y no otro** (botón vs icono vs tab vs menú).
- **Mapa de densidad**: qué información está en superficie, qué está a un
  hover/tooltip, qué está a un clic, qué nunca se muestra aquí.
- **Integración entre superficies**: qué hace cada una y cómo se conectan.
  No omitas ninguna relevante (p. ej. la extensión a nivel de contacto).
- **Plan técnico concreto**: archivos y módulos, por qué, cómo encaja.
- **Edge cases y su solución**, incluido el estado vacío útil.
- **Volumen**: qué pasa con 0, 12, 80 y 400 ítems. Scroll, paginación o
  búsqueda no se improvisan al implementar.
- **Entrega completa** cuando aplique: instalador/DMG, descarga Mac, logo.

## 3. Reglas de UX

- Menos clics: si un paso se puede inferir, se infiere.
- Esencial primero; detalle bajo demanda. No escondas el esencial.
- Transiciones suaves, sin saltos, parpadeos ni reordenaciones bruscas.
- Streaming (transcripción en chunks): unido y legible, nunca fragmentado.
  Comprueba el estado final al terminar de grabar.
- Cada pantalla: un foco y una acción principal evidente.
- Vacíos, carga y error siempre diseñados, nunca por defecto.
- La UI enseña usándose. Affordances visibles (agarrar, seleccionar,
  filtrar) sin tutorial. Si alguien no sabe qué se puede arrastrar o
  seleccionar, el affordance falta.

## 4. Sin AI slop

Todo texto generado por IA que vea el usuario (tareas, sugerencias, briefs,
tarjetas, emails) debe ser corto, directo y específico al contexto.

- Nada genérico, nada de relleno, nada de tono "asistente".
- Los emails deben sonar escritos por una persona con criterio.
- Criterio de aceptación: entra en el Definition of Done de cada feature
  que genere texto.

## 5. Checklist antes de dar algo por hecho

- [ ] ¿Reutiliza patrones y estilos existentes (`Button`, `IconAction`,
      tabs, tokens)?
- [ ] ¿Encaja visual y funcionalmente con las otras superficies?
- [ ] ¿Máxima información útil con mínima superficie? ¿Menos clics?
- [ ] ¿Cada control es el tipo correcto (no un botón donde basta un icono,
      no scroll infinito donde hace falta paginar)?
- [ ] ¿Iconos con tooltip + `aria-label`? ¿Sin labels hardcodeadas raras?
- [ ] ¿0 / muchos ítems resueltos (vacío, tabs, paginación, multi-select)?
- [ ] ¿La viewport principal cabe sin scroll de página? ¿El scroll está
      acotado al bloque que lo necesita?
- [ ] ¿Edge cases y estado vacío cubiertos y diseñados?
- [ ] ¿Textos de IA cortos, directos y sin slop?
- [ ] ¿Está claro qué archivos se tocan y por qué?

## 6. Proporcionalidad (peso visual acorde a la importancia)

- Acción principal = protagonista. Todo lo demás = enlace, icono o control
  compacto.
- Ajustes puntuales (idioma, login alternativo, preferencias) no ocupan
  espacio principal: van en ajustes, footer o enlace secundario.
- Máximo una línea de texto de apoyo, o ninguna. Si una función necesita
  un párrafo para entenderse, rediseña el flujo.
- Antes de añadir UI, prueba primero sin UI: detección, defaults, contexto.
- En superficies pequeñas (popup de extensión), una feature secundaria no
  quita espacio a la acción principal.
- Reutiliza variantes existentes (`ghost`, `link`, `icon`, `IconAction`)
  en lugar de crear botones nuevos.
- En el plan, para cada elemento nuevo: dónde, peso, por qué. Con captura
  o descripción, antes de implementar.

## 7. Pensar el recorrido

Antes de diseñar, sitúa la feature en el recorrido real. No lo inventes:
si el repo o los docs ya lo describen, úsalo; si no, declara supuestos.

**Preguntas**

- ¿Qué intenta lograr, qué acaba de hacer, qué hará después?
- ¿Con qué atención llega (prisa, otra ventana, concentrada)? La UI se
  dimensiona a esa atención.
- ¿Qué le cuesta más si falla: tiempo, confianza, o algo de cara a otros?
  Ahí el listón es impecable. En el resto: coherente y discreto.
- ¿Qué información necesita ahora, y cuál puede esperar?
- ¿Dónde espera encontrarlo en las otras superficies, sin repetir pasos?

**Edge cases: del recorrido, no del código**

- no hay nada (primera vez / cuenta vacía)
- datos a medias o de mala calidad
- interrupción (cierre, red, cambio de contexto)
- mucho más volumen del esperado
- fallo y retorno sin perder lo hecho

Para cada uno: qué ve y cómo sigue. Si no aplica, no lo rellenes.

**En el plan:** recorrido breve, momentos críticos, qué se prioriza en cada
uno, y el mapa de densidad (superficie / hover / clic / nunca aquí).
