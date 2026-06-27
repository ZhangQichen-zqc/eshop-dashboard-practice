FROM node:20-bookworm-slim

WORKDIR /app

# 使用国内 npm 镜像加速
RUN npm config set registry https://registry.npmmirror.com

COPY server/package*.json ./
RUN npm ci --omit=dev

COPY server/src ./src
COPY server/data ./data

ENV PORT=38173
EXPOSE 38173

CMD ["npm", "start"]
