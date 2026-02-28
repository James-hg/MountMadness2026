FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY src/index.html /usr/share/nginx/html/
COPY src/static/ /usr/share/nginx/html/static/
COPY src/auth/ /usr/share/nginx/html/auth/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
