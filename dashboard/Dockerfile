# Frontend Dockerfile for React Dashboard
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (including dev deps for vite)
RUN npm ci

# Copy source
COPY . .

# Set API URL for build (Vite embeds at build time)
ARG VITE_API_URL=https://api.trading.samaanai.com
ENV VITE_API_URL=${VITE_API_URL}

# Build for production
RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 8080 (Cloud Run requirement)
EXPOSE 8080

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
