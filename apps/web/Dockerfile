# syntax=docker/dockerfile:1
# Build context is the repo ROOT so npm workspaces resolve (@lighthouse/shared-types).
FROM node:20-bookworm-slim AS base
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

# ---- deps: install workspace dependencies (cached on manifest changes) ----
FROM base AS deps
COPY package.json package-lock.json* ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/shared-types/package.json ./packages/shared-types/package.json
RUN npm install

# ---- build: generate shared types, then build Next.js ----
FROM base AS build
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
# Next.js bakes rewrite() destinations at build time, so the same-origin /api proxy
# target must be known here (it's the api service on the compose network).
ARG INTERNAL_API_URL=http://api:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    INTERNAL_API_URL=$INTERNAL_API_URL \
    NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN node packages/shared-types/scripts/generate.mjs \
    && npm run build --workspace=apps/web

# ---- run: production server ----
FROM base AS run
ENV NODE_ENV=production
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/apps/web ./apps/web
COPY --from=build /app/packages/shared-types ./packages/shared-types
WORKDIR /app/apps/web
EXPOSE 3000
CMD ["npm", "run", "start"]
