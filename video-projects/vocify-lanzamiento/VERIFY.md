# VERIFY — Vocify lanzamiento ES (2026-10-02)

Entregable: `renders/vocify-lanzamiento-es.mp4` (1920×1080, 60 fps, 30.0 s, H.264 + AAC 256k, audio = `assets/audio/master.wav` remuxado).

| Check | Resultado |
|---|---|
| `hyperframes lint` | 0 errores (16 avisos de estructura: el skill pide un único `index.html`) |
| Cortes vs beat (128 BPM, fase 0) | 1.883 +8 ms · 7.500 0 · 13.133 +8 · 15.950 +12 · 18.750 0 · 22.983 +15 · 23.450 +12 · 23.917 +10 · 24.150 +9 (medio beat) |
| Drop (B20 = 9.375 s) | el detector lo marca en 9.433 (+58 ms): el corte real es papel → flash blanco, detectado cuando el flash cae a tinta |
| Luminancia por capítulo | 18 → 114-139 → 30-66 → 219-230 → 29-35 → 149-152 → 23-32 → 214-230 → flurry → 24-26 (alterna en cada capítulo) |
| Hueco pre-drop | RMS −39 dB en 9.25 s, −6 dB en el drop |
| Loudness | −14.0 LUFS integrado, LRA 4.1 LU |
| Tiras de transición | `qa/strips/strip-*.png` (B4, B10, B16, B20, B28, B34, B40, B48, B52, B57): sin capas fantasma ni atascadas |
| Prueba de marca | `qa/brand-test.png`: 6 frames aleatorios, todos se leen como Vocify sin HUD |

## Notas
- Música y SFX sintetizados (`scripts/synth-audio.mjs`, DSP determinista, 128 BPM exactos): los créditos de OpenRouter
  estaban agotados (uso $70.05 / $70) y la key de ElevenLabs en `~/dani/.env` no es un valor ASCII válido.
- Datos de cliente (Grupo Ibérica, Laura Méndez, 48.000 €, 6 h) son de demo dentro de la UI.

## v2 (2026-10-02): features más lentas, inicio más claro
Entregable: `renders/vocify-lanzamiento-es-v2.mp4` (49.7 s, 106 beats a 128 BPM).
- Intro: tras "todo empieza con tu voz" entra el mapa CAPTURA · AUTOMATIZA · ASISTE · APRENDE, una palabra por beat.
- Features: cada capítulo pasa de 4-8 a 8-22 beats; cada acción de UI tiene su beat propio; subtítulo explicativo por feature.
- Cortes: 3.750 0 · 14.067 +4 · 25.317 +4 · 30.950 +12 · 35.633 +8 · 42.200 +13 · 42.667 +10 · 43.133 +8 · 43.367 +7 (½) · 43.600 +6 · 43.833 +5 (½) ms. El drop (17.8125 s) se detecta a +71 ms por el flash papel→blanco→tinta.
- Loudness −13.9 LUFS. Tiras `qa/strips/v2-*.png` revisadas.
