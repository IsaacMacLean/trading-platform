#!/bin/bash
# ============================================================
# Trading Platform — One-Shot Server Setup
# Run this once on a fresh Ubuntu 22.04 VM as the ubuntu user
# ============================================================
set -e

echo ""
echo "=========================================="
echo "  Trading Platform Server Setup"
echo "=========================================="
echo ""

# --- System packages ---
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv git curl tzdata

# Set timezone to ET
sudo timedatectl set-timezone America/New_York
echo "  Timezone set to $(timedatectl | grep 'Time zone')"

# --- Clone repo ---
echo "[2/6] Setting up project..."
cd ~
if [ -d "trading-platform" ]; then
    echo "  Directory exists — pulling latest..."
    cd trading-platform
    git pull
else
    git clone https://github.com/YOUR_USERNAME/trading-platform.git
    cd trading-platform
fi

# --- Write .env ---
echo "[3/6] Writing credentials..."
cat > .env << 'ENVEOF'
ALPACA_API_KEY=PKJT5GNF6WZLAAALNQTS5X2Q56
ALPACA_SECRET_KEY=8nQ6hSRBPEndowhYGTuQAboiV85FFiDEHCgLoK9AGQz4
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2
ENVEOF
echo "  .env written."

# --- Python venv + deps ---
echo "[4/6] Installing Python dependencies..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Dependencies installed."

# --- systemd service: bot ---
echo "[5/6] Installing systemd services..."
sudo tee /etc/systemd/system/trading-bot.service > /dev/null << SERVICE
[Unit]
Description=Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/trading-platform
EnvironmentFile=/home/ubuntu/trading-platform/.env
ExecStart=/home/ubuntu/trading-platform/venv/bin/python main.py
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

# --- systemd service: dashboard ---
sudo tee /etc/systemd/system/trading-dashboard.service > /dev/null << SERVICE
[Unit]
Description=Trading Dashboard
After=network-online.target trading-bot.service
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/trading-platform
EnvironmentFile=/home/ubuntu/trading-platform/.env
ExecStart=/home/ubuntu/trading-platform/venv/bin/python run_dashboard.py
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable trading-bot trading-dashboard
sudo systemctl restart trading-bot trading-dashboard

# --- Open firewall for dashboard ---
echo "[6/6] Configuring firewall..."
sudo iptables -I INPUT -p tcp --dport 8050 -j ACCEPT
# Make it persist across reboots
sudo apt-get install -y iptables-persistent -qq
sudo netfilter-persistent save

echo ""
echo "=========================================="
echo "  Setup complete!"
echo ""
echo "  Bot status:"
sudo systemctl status trading-bot --no-pager -l | tail -5
echo ""
echo "  Dashboard:"
echo "  http://$(curl -s ifconfig.me):8050"
echo ""
echo "  Useful commands:"
echo "  sudo journalctl -u trading-bot -f        # live logs"
echo "  sudo systemctl restart trading-bot        # restart"
echo "  sudo systemctl stop trading-bot           # stop"
echo "=========================================="
