#!/bin/bash
set -e

# Ensure required directories exist
mkdir -p "$DATA_DIR"
mkdir -p "$SERVER_DATA_DIR"
mkdir -p /var/log/supervisor
mkdir -p /app/server/tmp
mkdir -p /app/server/tmp   # piper writes intermediate wav files here

# If SERVER_HOST is still the placeholder, try to auto-detect the container IP
if [ "$SERVER_HOST" = "localhost" ] || [ -z "$SERVER_HOST" ]; then
    # For local deployment; override with SERVER_HOST env var for remote access
    export SERVER_HOST=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "localhost")
fi

echo "Starting Xiaozhi Custom Server"
echo "  Web UI:         http://$SERVER_HOST:$FLASK_PORT"
echo "  WebSocket:      ws://$SERVER_HOST:$WS_PORT/xiaozhi/v1/"
echo "  Vision HTTP:    http://$SERVER_HOST:$HTTP_PORT/mcp/vision/explain"
echo ""
echo "Set SERVER_HOST env var to your Jetson's LAN IP for ESP32 devices to connect."
echo ""

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
