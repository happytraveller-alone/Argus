# argus agent-engine sidecar — Node.js (>=22.19.0), ESM-only.
# Reuses pi packages (@earendil-works/pi-ai, @earendil-works/pi-agent-core) from npm.
# Build context is the agent-engine/ directory:
#   docker build -f docker/agent-engine.Dockerfile ./agent-engine
# node:22-slim (glibc) is used rather than alpine because @earendil-works/pi-ai
# bundles the AWS SDK, which is happier on glibc.

# ---- build stage -------------------------------------------------------------
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# ---- runtime stage -----------------------------------------------------------
FROM node:22-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund
COPY --from=build /app/dist ./dist

ENV AGENT_ENGINE_PORT=18100
ENV AGENT_ENGINE_HOST=0.0.0.0
EXPOSE 18100

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.AGENT_ENGINE_PORT||18100)+'/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "dist/server.js"]
