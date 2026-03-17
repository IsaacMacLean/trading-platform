# Deploying the Trading Bot (Free, 24/7)

## Recommended: Oracle Cloud Free Tier (Always Free VM)

Oracle offers a genuinely free VM that never expires — 1 GB RAM, 1 OCPU, 47 GB storage.

### 1. Create a Free Oracle Cloud Account
1. Go to https://cloud.oracle.com and sign up for a free account.
2. Choose your home region (pick one close to you — it can't be changed later).
3. A credit card is required for verification but **you will not be charged** if you stay within Always Free resources.

### 2. Launch a Free VM
1. In the Oracle Cloud Console, go to **Compute > Instances > Create Instance**.
2. Choose **VM.Standard.E2.1.Micro** (Always Free eligible).
3. Select **Ubuntu 22.04** as the OS image.
4. Download the generated SSH key pair and save it securely.
5. Click **Create**.

### 3. Connect to Your VM
```bash
chmod 400 ~/Downloads/your-key.key
ssh -i ~/Downloads/your-key.key ubuntu@<your-vm-public-ip>
```

### 4. Set Up the Environment
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python
sudo apt install python3 python3-pip python3-venv -y

# Clone your repo (or upload files via scp)
git clone https://github.com/your-username/trading-platform.git
cd trading-platform

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 5. Add Your Secrets
```bash
nano .env
# Paste your ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL
# Save with Ctrl+O, exit with Ctrl+X
```

### 6. Run the Bot 24/7 with systemd

Create a service file so the bot restarts automatically on crash or reboot:

```bash
sudo nano /etc/systemd/system/trading-bot.service
```

Paste the following (update paths as needed):
```ini
[Unit]
Description=Trading Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/trading-platform
EnvironmentFile=/home/ubuntu/trading-platform/.env
ExecStart=/home/ubuntu/trading-platform/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot

# Check status
sudo systemctl status trading-bot

# View live logs
sudo journalctl -u trading-bot -f
```

---

## Alternative Free Options

| Platform | Free Tier | Limitation |
|----------|-----------|------------|
| **Render** | 750 hrs/month | Spins down after 15 min of inactivity |
| **Railway** | $5 free credit/month | Depletes over time |
| **Fly.io** | 3 shared-cpu VMs | May require credit card |
| **Google Cloud** | e2-micro (always free) | US regions only |

> Oracle Cloud is the most reliable free option for a long-running bot with no sleep/spin-down behavior.

---

## Keeping Your Bot Updated

```bash
# SSH into your VM, then:
cd trading-platform
git pull
sudo systemctl restart trading-bot
```
