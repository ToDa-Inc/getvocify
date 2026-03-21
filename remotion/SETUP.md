# Quick Start Guide for Vocify Video

## 📦 Installation

1. **Navigate to the remotion directory:**
```bash
cd remotion
```

2. **Install dependencies:**
```bash
npm install
```

This will install Remotion, React, and TypeScript.

## 🎬 Run Remotion Studio

**Start the development server:**
```bash
npm start
```

This opens **Remotion Studio** in your browser where you can:
- ▶️ Play the video
- ⏸️ Pause and scrub through frames
- 🔄 See live updates as you edit code
- ⚙️ Preview rendering settings

## 🎥 Render Final Video

**Render the MP4 file:**
```bash
npm run build-output
```

This creates `out.mp4` (about 50-70MB depending on settings).

## 📝 What's Included

The project has **7 animated scenes**:

1. **Intro (0-8s)** - Vocify logo and main headline
2. **Problem (8-16s)** - €12,400 annual loss figure
3. **Solution (16-24s)** - 3 main features with cards
4. **WhatsApp (24-32s)** - Phone mockup with chat bubbles
5. **Chrome Extension (32-40s)** - Browser extension mockups
6. **Integrations (40-48s)** - CRM ecosystem
7. **CTA (48-56s)** - Call to action final slide

Each scene has smooth fade-in animations and professional transitions.

## 🎨 Customization

### Change Scene Duration
Edit `src/lib/constants.ts`:
```typescript
export const SCENE_DURATION = 8 * COMP_FPS; // 8 seconds per scene
```

### Edit Scene Content
Open the scene file you want to change:
- `src/compositions/scenes/IntroScene.tsx`
- `src/compositions/scenes/ProblemScene.tsx`
- etc.

Make changes and Remotion will hot-reload!

### Update Colors
Edit `src/lib/constants.ts` colors object:
```typescript
export const COLORS = {
  beige: 'hsl(35, 25%, 35%)',    // Main brand color
  cream: 'hsl(40, 33%, 96%)',    // Background
  // ...
}
```

## 📊 Video Specs

- **Size:** 1920x1080 (Full HD)
- **Frame Rate:** 30 FPS
- **Duration:** ~60 seconds (240 scenes × 30fps = 7200 frames)
- **Format:** H.264 MP4
- **Quality:** CRF 18 (professional quality)

## 🎯 Next Steps

### To add voiceover:
1. Record voiceover as MP3
2. Place in `public/voiceover.mp3`
3. Import and add to any scene:
```typescript
import { Audio } from 'remotion';
<Audio src={require('/voiceover.mp3')} />
```

### To add background music:
1. Add MP3 to `public/music.mp3`
2. Use `Audio` component with volume adjustment
3. Trim to match video duration

### To add sound effects:
1. Create a new file: `src/lib/audio.ts`
2. Import sound effects
3. Use in scenes with `Audio` component

## 🚀 Export Options

### High Quality (Professional)
```bash
remotion render index.ts vocify-demo --codec=prores --prores-profile=hq
```

### Web Optimized (Smaller file)
```bash
remotion render index.ts vocify-demo --codec=h264 --crf 23
```

### With Custom Output
```bash
remotion render index.ts vocify-demo -o ./my-video.mp4
```

## 📚 Learn More

- [Remotion Documentation](https://www.remotion.dev/docs)
- [Animation Guide](https://www.remotion.dev/docs/animate)
- [Sequence & Timing](https://www.remotion.dev/docs/sequencing)

## 🆘 Troubleshooting

**Port already in use?**
```bash
npm start -- --port 3001
```

**Need to clear cache?**
```bash
rm -rf node_modules/.cache
npm start
```

**Video won't render?**
- Check Node.js version (14+)
- Update Remotion: `npm update remotion @remotion/cli`
- Check console for errors

## 💾 Project Structure

```
remotion/
├── src/
│   ├── Root.tsx                 # Main entry
│   ├── index.ts                 # Registration
│   ├── compositions/
│   │   ├── VocifyDemoVideo.tsx # Video orchestrator
│   │   └── scenes/              # 7 scene components
│   └── lib/
│       ├── constants.ts         # Colors & timing
│       └── animations.ts        # Animation helpers
├── package.json
├── tsconfig.json
└── README.md                    # Full documentation
```

---

**Enjoy! Your professional Vocify demo video is ready to go.** 🎉
