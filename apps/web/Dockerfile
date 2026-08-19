# ── Stage 1: Prune monorepo to web scope ───────────────────────────────────
FROM oven/bun:1.2-alpine AS pruner

RUN apk add --no-cache nodejs libc6-compat
RUN bun add -g turbo@^2

WORKDIR /app
COPY . .
RUN turbo prune --scope=@openhuman/web --out-dir=out --docker

# ── Stage 2: Install deps & build ──────────────────────────────────────────
FROM oven/bun:1.2-alpine AS builder

RUN apk add --no-cache nodejs libc6-compat

WORKDIR /app

COPY --from=pruner /app/out/json/ .
COPY --from=pruner /app/out/bun.lock ./bun.lock
RUN bun install

COPY --from=pruner /app/out/full/ .

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

RUN bun run build --filter=@openhuman/web

# ── Stage 3: Runtime ────────────────────────────────────────────────────────
FROM oven/bun:1.2-alpine AS runner

RUN apk add --no-cache nodejs libc6-compat

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

COPY --from=builder /app/apps/web/public ./apps/web/public
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "apps/web/server.js"]
