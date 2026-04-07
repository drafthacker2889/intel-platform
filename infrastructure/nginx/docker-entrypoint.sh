#!/bin/sh
set -eu

: "${ACTIVE_UI_UPSTREAM:=dashboard-ui:80}"

envsubst '${ACTIVE_UI_UPSTREAM}' < /etc/nginx/templates/gateway.template.conf > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
