/// <reference types="vite/client" />

declare module '*.svg' {
  const src: string
  export default src
}

interface ImportMetaEnv {
  readonly DEV: boolean
  readonly PROD: boolean
  readonly MODE: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
