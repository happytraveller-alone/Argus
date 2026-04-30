import { defineConfig, type ConfigEnv } from "vite";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";
import path from "path";
import { createChunkObfuscatorPlugin } from "./scripts/chunkObfuscatorPlugin";

export default defineConfig(({ mode }: ConfigEnv) => {
  const isProduction = mode === "production";

  const obfuscatorPlugin = isProduction ? createChunkObfuscatorPlugin() : null;

  return {
  envDir: path.resolve(__dirname, "../docker/env/frontend"),
  plugins: [
    react(),
    svgr({
      svgrOptions: {
        icon: true,
        exportType: "named",
        namedExport: "ReactComponent",
      },
    }),
    ...(obfuscatorPlugin ? [obfuscatorPlugin] : []),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      onwarn(warning, warn) {
        if (warning.id?.includes('node_modules')) return;
        warn(warning);
      },
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          ui: [
            '@radix-ui/react-dialog',
            '@radix-ui/react-select',
            '@radix-ui/react-tabs',
            '@radix-ui/react-progress'
          ],
          charts: ['recharts'],
          ai: ['@google/generative-ai'],
          utils: ['clsx', 'tailwind-merge', 'date-fns', 'sonner']
        },
      },
    },
    chunkSizeWarningLimit: 1000,
    sourcemap: false,
    minify: 'esbuild',
  },
  cacheDir: process.env.VITE_CACHE_DIR ?? 'node_modules/.vite',
  esbuild: isProduction ? {
    drop: ['console', 'debugger'],
  } : {},
  server: {
    port: 5173,
    host: true,
    open: process.env.VITE_OPEN_BROWSER === "1",
    hmr: process.env.VITE_HMR_CLIENT_PORT
      ? { clientPort: parseInt(process.env.VITE_HMR_CLIENT_PORT, 10) }
      : true,
    cors: {
      origin: true,
      credentials: true,
      methods: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
      allowedHeaders: [
        "Authorization",
        "Content-Type",
        "X-DashScope-SSE",
        "X-Requested-With",
      ],
    },
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
      "/dashscope-proxy": {
        target: "https://dashscope.aliyuncs.com",
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(/^\/dashscope-proxy/, ""),
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("origin", "https://dashscope.aliyuncs.com");
          });
        },
      },
    },
  },
  preview: {
    port: 5173,
    host: true,
  },
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-router-dom',
      '@google/generative-ai',
      'recharts',
      'sonner'
    ],
  },
  };
});
