FROM node:22.12.0-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM dependencies AS development
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]

FROM dependencies AS build
COPY . .
RUN npm run build

FROM nginx:1.27.3-alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
