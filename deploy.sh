#!/bin/bash
# Run this on the Hetzner server as root to set up the Assistant app.
set -e

DOMAIN="mcgreeff-assistant.duckdns.org"
EMAIL="christiaangreeff@gmail.com"
APP_DIR="/opt/assistant"

echo "=== 1. Updating system ==="
apt update && apt upgrade -y

echo "=== 2. Installing dependencies ==="
apt install -y python3 python3-venv python3-pip nodejs npm nginx git certbot python3-certbot-nginx

echo "=== 3. Cloning repo ==="
if [ -d "$APP_DIR" ]; then
  cd "$APP_DIR" && git pull
else
  git clone https://github.com/Meserlion/Assisstant.git "$APP_DIR"
fi

echo "=== 4. Setting up backend ==="
cd "$APP_DIR/backend"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p "$APP_DIR/data"

echo "=== 5. Creating .env if missing ==="
if [ ! -f "$APP_DIR/backend/.env" ]; then
  cp "$APP_DIR/backend/.env.example" "$APP_DIR/backend/.env"
  echo ""
  echo ">>> ACTION REQUIRED: Fill in your API keys in $APP_DIR/backend/.env <<<"
  echo ""
fi

echo "=== 6. Building frontend ==="
cd "$APP_DIR/frontend"
npm install
npm run build

echo "=== 7. Creating systemd service ==="
cat > /etc/systemd/system/assistant.service << EOF
[Unit]
Description=Assistant API
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR/backend
Environment=PATH=$APP_DIR/backend/venv/bin
ExecStart=$APP_DIR/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable assistant
systemctl restart assistant

echo "=== 8. Configuring nginx ==="
cat > /etc/nginx/sites-available/assistant << 'NGINXCONF'
server {
    listen 80;
    server_name mcgreeff-assistant.duckdns.org;

    location / {
        root /opt/assistant/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 50M;
    }
}
NGINXCONF

ln -sf /etc/nginx/sites-available/assistant /etc/nginx/sites-enabled/assistant
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "=== 9. Getting SSL certificate ==="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect

echo ""
echo "=== Done! ==="
echo "App is running at https://$DOMAIN"
echo ""
echo "If you haven't yet, edit your API keys:"
echo "  nano $APP_DIR/backend/.env"
echo "Then restart: systemctl restart assistant"
