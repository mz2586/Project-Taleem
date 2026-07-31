# syntax=docker/dockerfile:1
# Project Taleem — Web PWA (Next.js) for container deploys (Koyeb/Docker).
# Multi-stage, non-root, self-contained (Next.js standalone output). NEXT_PUBLIC_API_URL is a build
# arg because Next inlines NEXT_PUBLIC_* at build time — set it to the backend's public URL.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=8000 \
    HOSTNAME=0.0.0.0
RUN useradd --create-home --uid 10001 taleem
# Next.js standalone bundle (server.js + minimal node_modules) + static assets + public.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER taleem
EXPOSE 8000
# Koyeb/Docker inject PORT; the standalone server honours PORT + HOSTNAME.
CMD ["node", "server.js"]
