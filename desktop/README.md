# Vocify Companion

Desktop app for [Vocify](https://github.com/ToDa-Inc/getvocify): Granola-style **system audio + mic**, dashboard UI, tray, always-on-top overlay. Talks to the production API at **https://api.getvocify.com/api/v1**.

Canonical repo (once populated): **https://github.com/ToDa-Inc/getvocify-desktop**

## If your prompt is `desktop $`

You are **already** in this folder. There is no `getvocify` directory here, so this fails:

```bash
cd getvocify
# bash: cd: getvocify: No such file or directory
```

```bash
pwd          # .../getvocify/desktop  (in this VM: /workspace/desktop)
npm start    # start the companion from here
cd ..        # getvocify repo root (in this VM: /workspace)
```

This Cursor cloud VM is Linux. An Electron window here does **not** appear on your Mac. To see the real app, clone and run on your Mac (below).

## Run on your Mac

Until `getvocify-desktop` has commits, clone **this** branch of getvocify:

```bash
git clone -b cursor/field-extraction-speakers-desktop-a838 https://github.com/ToDa-Inc/getvocify.git
cd getvocify/desktop
npm install
npm start
```

A window and a menu-bar icon should appear. Log in with the same Vocify account as [app.getvocify.com](https://app.getvocify.com).

Once https://github.com/ToDa-Inc/getvocify-desktop has code:

```bash
git clone https://github.com/ToDa-Inc/getvocify-desktop.git
cd getvocify-desktop
npm install
npm start
```

## Installer (.dmg)

On a Mac:

```bash
npm run dist:mac
open dist/Vocify-Companion-0.2.0.dmg
```

Or GitHub → Actions → **Mac DMG** / **Companion Mac DMG** → download the artifact. Unsigned: **Right-click → Open**. Grant Microphone + Screen Recording.

## API

Default `VOCIFY_API` / login field: `https://api.getvocify.com/api/v1`. Local backend: `http://localhost:8888/api/v1`.
