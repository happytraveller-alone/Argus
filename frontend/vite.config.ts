import { defineConfig, type ConfigEnv } from "vite";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";
import path from "path";

// https://vite.dev/config/
export default defineConfig(({ mode }: ConfigEnv) => {
  const isProduction = mode === "production";

  // 仅在生产构建时加载混淆插件，避免开发模式性能损耗
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const obfuscatorPlugin = isProduction
    ? (() => {
        const { default: javascriptObfuscator } = require("vite-plugin-javascript-obfuscator");
        return javascriptObfuscator({
          options: {
            // 标识符混淆（低成本高收益）
            identifierNamesGenerator: "hexadecimal",
            renameGlobals: false,        // 不重命名全局：避免破坏 React 运行时

            // 字符串混淆（中等成本，SSE 安全）
            stringArray: true,
            stringArrayEncoding: ["base64"],
            stringArrayThreshold: 0.75,  // 75% 字符串被混淆
            stringArrayRotate: true,
            stringArrayShuffle: true,
            splitStrings: false,          // 关闭：避免破坏 EventSource URL 构造

            // 关闭高风险选项
            controlFlowFlattening: false, // 关闭：构建时间翻倍，SSE 处理器有风险
            selfDefending: false,         // 关闭：与 React 不兼容
            debugProtection: false,       // 关闭：会破坏 SSE DevTools 调试

            // 适度保护
            disableConsoleOutput: true,
            deadCodeInjection: false,     // 关闭：显著增加包体积
            unicodeEscapeSequence: false, // 关闭：大幅增加体积

            // 构建配置
            sourceMap: false,
            target: "browser",
          },
          // 只混淆应用自身入口 chunk，跳过第三方依赖 chunk
          include: ["**/assets/index-*.js"],
          exclude: [
            "**/assets/vendor-*.js",
            "**/assets/charts-*.js",
            "**/assets/ai-*.js",
            "**/assets/ui-*.js",
            "**/assets/utils-*.js",
          ],
        });
      })()
    : null;

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
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
  },
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
