FROM --platform=linux/amd64 ghcr.io/frappe/crm:v1.88.0@sha256:5fad619652bf5f3c0313784b37b11958b8ae0341cd64c298cec14b8e0d581c63

USER frappe
WORKDIR /home/frappe/frappe-bench
ENV NODE_OPTIONS=--max-old-space-size=2048
ENV PYTHONDONTWRITEBYTECODE=1
ARG FRAPPE_UI_REF=4515014c87ece6cb20ee91d2cfb121c5cbd1ff4a
RUN git init /tmp/framework-ui \
    && git -C /tmp/framework-ui remote add origin https://github.com/frappe/frappe \
    && git -C /tmp/framework-ui fetch --depth 1 origin "$FRAPPE_UI_REF" \
    && git -C /tmp/framework-ui checkout FETCH_HEAD -- ui \
    && rm -rf apps/frappe/ui \
    && mv /tmp/framework-ui/ui apps/frappe/ui \
    && rm -rf /tmp/framework-ui

COPY --chown=frappe:frappe . apps/crm
COPY --chown=frappe:frappe extensions/recuite_billing apps/recuite_billing
RUN env/bin/pip install -e apps/crm \
    && env/bin/pip install --no-deps -e apps/recuite_billing \
    && ls -1 apps > sites/apps.txt \
    && env/bin/python -c 'import frappe,crm,recuite_billing; assert frappe.__version__ == "15.123.1"; assert crm.__version__ == "1.88.0"' \
    && wkhtmltopdf --version

RUN if [ ! -e sites/assets ]; then ln -s /home/frappe/frappe-bench/assets sites/assets; fi \
    && bench build --app crm
