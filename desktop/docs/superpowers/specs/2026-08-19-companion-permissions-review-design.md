# Vocify Companion — permissions, dual-channel capture, CRM review

**Date:** 2026-08-19  
**Status:** Approved (user: A+B, HubSpot approve in-app, tokenized theme, Anarlog capture architecture)

## Goal

Mac users grant Microphone + Screen & System Audio the way Granola/Anarlog do. Listen captures **system audio = prospect** and **mic = sales**. Stop extracts notes and HubSpot fields in the companion window; the rep edits/omits and Approve writes CRM.

## Non-goals

Vendor Anarlog’s Tauri/Rust tree, local STT, Accessibility overlay, calendar sync, AEC crate, React dashboard rewrite.

## Units

| Unit | Responsibility |
|------|----------------|
| `renderer/theme.css` | Tokens only (paper vs glass, Vocify cream/beige) |
| `lib/permissions.js` | Status, request vs open-settings, deep links |
| `lib/mic-devices.js` | Exclude `vocify-audio-tap` from mic |
| `lib/system-audio.js` | Linux PipeWire/Pulse; macOS ScreenCaptureKit helper; else Chromium |
| `lib/extraction-omit.js` | Same omit/approve contract as the Chrome extension |
| `lib/memo-review.js` | upload-and-extract → poll → deal pick → approve payload |
| `native/macos-tap` | SCK audio-only → s16le stdout |

Listen is blocked until both macOS permissions are authorized.
