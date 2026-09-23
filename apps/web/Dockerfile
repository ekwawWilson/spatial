# Development image for the web app. Dependencies are installed at build time
# inside the image; docker-compose mounts only source folders, so the container
# never writes node_modules (as root) into the working tree.
FROM node:24-alpine

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /repo

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY packages/map-core/package.json packages/map-core/
COPY apps/web/package.json apps/web/
RUN pnpm install --frozen-lockfile

COPY packages/map-core packages/map-core
COPY apps/web apps/web

EXPOSE 5173
CMD ["pnpm", "--filter", "@spatial/web", "dev", "--host", "0.0.0.0"]
