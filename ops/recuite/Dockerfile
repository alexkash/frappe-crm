# The upstream CRM image currently contains only Framework. Install our app explicitly.
FROM ghcr.io/frappe/crm:v1.88.0@sha256:5fad619652bf5f3c0313784b37b11958b8ae0341cd64c298cec14b8e0d581c63

ARG CRM_REPOSITORY=https://github.com/alexkash/frappe-crm
ARG CRM_REF=recuite-v1.88.0-20261017

USER frappe
WORKDIR /home/frappe/frappe-bench
ENV NODE_OPTIONS=--max-old-space-size=1536

RUN test ! -e sites/assets \
    && ln -s /home/frappe/frappe-bench/assets sites/assets \
    && bench get-app --skip-assets --branch "$CRM_REF" crm "$CRM_REPOSITORY" \
    && bench build --app crm \
    && test -d apps/crm \
    && test -s apps/crm/crm/public/frontend/index.html \
    && test -s apps/crm/crm/www/crm.html \
    && env/bin/python -c 'import crm,frappe; assert crm.__version__ == "1.88.0"; assert frappe.__version__ == "15.123.1"' \
    && rm -rf apps/crm/.git apps/crm/node_modules apps/crm/frontend/node_modules

LABEL org.opencontainers.image.source=https://github.com/alexkash/frappe-crm
