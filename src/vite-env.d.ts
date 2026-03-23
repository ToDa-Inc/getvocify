/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Wistia embed hashed ID (video page → Embed & Share) */
  readonly VITE_WISTIA_MEDIA_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
