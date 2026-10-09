# BRAND — Vocify (lanzamiento, ES)

## Concepto (de Dani, 2026-10-02)
Capturar · Automatizar · Asistir · Aprender. El poder principal: **captura donde estés**
(SDR, AE o comercial de campo). Después automatizamos, te asistimos en la llamada
(objeciones, preguntas de producto) y te damos coaching para mejorar.

## Color (fuentes en el repo)
| Token | Valor | Fuente |
|---|---|---|
| ink | `hsl(30 15% 8%)` → `#17140f` | `desktop/renderer/tokens.css` `--ink` |
| paper / cream | `hsl(40 33% 96%)` → `#f8f5f0` | `--cream` |
| cream-dark | `hsl(38 25% 88%)` → `#e8e0d3` | `--cream-dark` |
| beige (marca, sobre claro) | `hsl(35 25% 35%)` → `#705a43` | `--beige` |
| beige isla (sobre oscuro) | `hsl(35 30% 86%)` HSB → `#dbc39a` | `IslandStyle.beige` (MeetingPill.swift) |
| oro del logo | `#c39a5c` → `#a87f45` | `public/icons/logo_transparent.png` |
| rojo REC | HSB(0, 66%, 86%) → `#db4a4a` | `IslandStyle.danger` |
| **verde (reservado al clímax)** | `#3fbf6a` | "HubSpot & Salesforce Updated" en `public/og-image.png` |

## Tipografía
- Display + UI: **Geist** (variable, `public/fonts/Geist-Variable.woff2`)
- Voz humana / acento: **Instrument Serif Italic** (la web la importa de Google Fonts)
- Capa máquina (HUD): **Geist Mono**

## La isla (getvocify-desktop/apps/macos/Sources/VocifyCompanion/MeetingPill.swift)
- Negro sólido junto a la cámara (notch); abierta = cristal oscuro con brillo arriba, borde de luz 1px
  (gradiente 0.34 → 0.08 → 0.24 blanco), radio inferior 12 (cerrada) / 22 (abierta).
- Orejas de 82pt: izquierda punto rojo REC 7pt + tiempo `00:12` monoespaciado; derecha onda de voz
  de 5 cápsulas (alturas 3/4.5/6/4.5/3, beige si hablas tú, blanco si ellos) + flecha.
- Burbujas: tú = beige oscuro `HSB(36,30%,34%)`, ellos = blanco 13%, radio 14, etiqueta beige.
- Ayuda en directo: "✦" + etiqueta beige, frase puente en cursiva, respuesta en 12.5 medium, "luego pregunta" secundaria.
- Tarjeta post-llamada: filas de cambios (checkbox, etiqueta, antes → después), "Aprobar N", "Revisar",
  "Actualizado en HubSpot · N campos", "Email a X listo", "Reunión … añadida".

## Coaching (shared/ui/i18n.js, es)
"Bien hecho", "La próxima vez", "Prueba con", "Siguiente paso acordado", "Cumplimiento del playbook en tus
últimas llamadas de este tipo". Objeciones: Precio, Ya usa otra herramienta, No es el momento…

## Frases de marca verificadas
- "Voice to CRM in 40 Seconds." / "Stop typing. Start closing." (`public/og-image.png`) → ES: "De la voz al CRM en 40 segundos."
- Integraciones: HubSpot y Salesforce (og-image). Canales: WhatsApp y web (og-image).

## Motivo
El **punto dorado** (la voz). Rebota, se estira en la isla, se vuelve la onda de 5 barras, explota en
palabras que escriben el CRM, se vuelve las barras de cumplimiento del playbook y aterriza como el
punto de la **i** de Vocify.

## Datos de demo (UI simulada, no afirmaciones)
Cliente ficticio "Grupo Ibérica", contacto "Laura Méndez". Cifras dentro de la UI (48.000 €, 6 h) son de demo.
