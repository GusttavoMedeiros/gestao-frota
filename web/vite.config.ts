import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  build: {
    outDir: '../frontend',
    emptyOutDir: true
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/icon.svg', 'icons/apple-touch-icon.svg'],
      manifest: {
        name: 'KG Frota',
        short_name: 'KG Frota',
        description: 'Gestao de frota, documentos, abastecimentos e manutencoes.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#f4f7f4',
        theme_color: '#12372f',
        icons: [
          {
            src: '/icons/icon.svg',
            sizes: '192x192',
            type: 'image/svg+xml',
            purpose: 'any maskable'
          },
          {
            src: '/icons/apple-touch-icon.svg',
            sizes: '180x180',
            type: 'image/svg+xml'
          }
        ]
      },
      workbox: {
        navigateFallback: '/',
        globPatterns: ['**/*.{js,css,html,svg,png,ico}']
      }
    })
  ]
});
