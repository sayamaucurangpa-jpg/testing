FROM php:8.2-cli

WORKDIR /app
COPY vulnerable /app

EXPOSE 8000
CMD ["php", "-S", "0.0.0.0:8000", "-t", "/app"]
