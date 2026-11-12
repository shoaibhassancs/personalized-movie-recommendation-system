# PMRS frontend image (Step 31): build the static site, then serve it with nginx as a
# non-root user. Local use only. VITE_API_URL is baked into the JavaScript at BUILD time
# (it is a public address, never a secret), so changing it means rebuilding.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_URL=http://127.0.0.1:8000
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
