FROM node:22-bookworm-slim
RUN apt-get update && apt-get install --yes --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install --global @openai/codex@0.167.0 && npm cache clean --force
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY src ./src
COPY public ./public
COPY MCP.md ./MCP.md
RUN mkdir -p /app/reports /home/node/.codex && chown -R node:node /app /home/node/.codex
USER node
CMD ["node", "src/server.js"]
