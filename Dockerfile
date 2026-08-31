FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
ARG SITE_URL=http://localhost:3000
ENV SITE_URL=$SITE_URL
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000 \
    SITE_URL=http://localhost:3000
COPY --from=build /app .
EXPOSE 3000
CMD ["npm", "run", "start"]
