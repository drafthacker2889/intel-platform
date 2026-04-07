FROM nginx:1.27-alpine

RUN apk add --no-cache gettext

COPY gateway.template.conf /etc/nginx/templates/gateway.template.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

CMD ["/docker-entrypoint.sh"]
