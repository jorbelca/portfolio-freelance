FROM python:3.13-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN mkdir /data && chown 1000:1000 /data
COPY comun.py app.py destino_demo.py interfaz.html verificar.py ./
USER 1000:1000
CMD ["python", "app.py"]

FROM python:3.13-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a AS proxy
RUN apk add --no-cache squid=7.6-r0
COPY proxy.conf /etc/squid/squid.conf
USER squid
CMD ["squid", "-N", "-f", "/etc/squid/squid.conf"]
