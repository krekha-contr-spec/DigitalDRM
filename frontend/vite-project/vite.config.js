// import { defineConfig } from 'vite'
// import react from '@vitejs/plugin-react'
// import tailwindcss from '@tailwindcss/vite'

// export default defineConfig({
//   plugins: [
//     react(),
//     tailwindcss(),
//   ],
// })
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/postcss'

export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on all interfaces (not just localhost) so the app is
    // reachable at http://10.41.10.13:<port> from other machines on
    // the local network, not just from the server i
    host: true,
    port: 5173,
  },
  preview: {
    host: true,
    port: 4173,
  },
})