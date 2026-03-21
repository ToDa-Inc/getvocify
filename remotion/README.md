# Vocify Animated Product Demo

A professional 60-second animated product demo video for Vocify, built with Remotion and React.

## Features

- **7 Animated Scenes** showcasing key Vocify features
  - Intro with branding
  - Problem statement (€12,400 annual loss)
  - Solution overview (3 main features)
  - WhatsApp integration demo
  - Chrome extension showcase
  - CRM integrations
  - Final CTA

- **Smooth Animations** using Remotion's interpolation and easing
- **Brand Colors** from the Vocify deck (beige, cream, foreground)
- **Professional Design** matching the VC pitch deck aesthetic
- **Responsive Layout** for 1920x1080 @ 30fps

## Setup

```bash
cd remotion
npm install
```

## Development

Preview the video in the browser:

```bash
npm start
```

This opens Remotion Studio where you can:
- Play/pause the video
- Scrub through timeline
- Adjust timing and animations
- Preview at different frame rates

## Build

Render the final MP4 video:

```bash
npm run build-output
```

This creates `out.mp4` in the remotion directory.

## Customization

### Change Colors
Edit `src/lib/constants.ts`:
```typescript
export const COLORS = {
  cream: 'hsl(40, 33%, 96%)',
  beige: 'hsl(35, 25%, 35%)',
  // ...
}
```

### Adjust Scene Duration
Edit `src/lib/constants.ts`:
```typescript
export const SCENE_DURATION = 8 * COMP_FPS; // Change 8 to desired seconds
```

### Modify Scene Content
Edit individual scene files in `src/compositions/scenes/`:
- `IntroScene.tsx` - Title and branding
- `ProblemScene.tsx` - Problem statement
- `SolutionScene.tsx` - Main features
- `WhatsAppScene.tsx` - WhatsApp experience
- `ChromeExtensionScene.tsx` - Browser extension
- `IntegrationsScene.tsx` - CRM integrations
- `CTAScene.tsx` - Call to action

### Add Voiceover
Add audio file to `public/voiceover.mp3` and update a scene:
```typescript
import { Audio } from 'remotion';

<Audio src={require('/voiceover.mp3')} />
```

## Video Specs

- **Resolution:** 1920x1080 (Full HD)
- **Frame Rate:** 30 FPS
- **Duration:** ~60 seconds
- **Codec:** H.264 (MP4)
- **Quality:** CRF 18 (high quality)

## Architecture

```
src/
├── index.ts                 # Entry point
├── Root.tsx                 # Main composition setup
├── compositions/
│   ├── VocifyDemoVideo.tsx # Video sequencer
│   └── scenes/              # Individual scene components
│       ├── IntroScene.tsx
│       ├── ProblemScene.tsx
│       ├── SolutionScene.tsx
│       ├── WhatsAppScene.tsx
│       ├── ChromeExtensionScene.tsx
│       ├── IntegrationsScene.tsx
│       └── CTAScene.tsx
└── lib/
    ├── constants.ts        # Colors, timing, dimensions
    └── animations.ts       # Animation utilities
```

## Tips

- Use `useCurrentFrame()` to access current frame number
- Use `Sequence` to layer scenes and control timing
- Use `interpolate()` from remotion for smooth animations
- Test animations in Remotion Studio before rendering
- Higher CRF values (0-51) = lower quality/faster render
- Use `--codec=prores` for higher quality or professional workflows

## Next Steps

1. ✅ Scenes created and animated
2. 📊 Add voiceover narration (optional)
3. 🎵 Add background music
4. 🔊 Add sound effects for transitions
5. 📤 Export and share

## Resources

- [Remotion Docs](https://www.remotion.dev/docs)
- [Remotion Animations](https://www.remotion.dev/docs/animate)
- [Remotion Composition](https://www.remotion.dev/docs/composition)
