#!/bin/bash
# IB Gateway Installation Script

set -e

echo "=== Installing Java ==="
sudo apt update
sudo apt install -y openjdk-11-jre-headless unzip wget

echo "=== Downloading IB Gateway ==="
cd ~
wget -q https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh
chmod +x ibgateway-stable-standalone-linux-x64.sh

echo "=== Installing IB Gateway (silent mode) ==="
./ibgateway-stable-standalone-linux-x64.sh -q -dir ~/Jts/ibgateway

echo "=== Downloading IBC ==="
wget -q https://github.com/IbcAlpha/IBC/releases/download/3.18.0/IBCLinux-3.18.0.zip
unzip -q IBCLinux-3.18.0.zip -d ~/ibc
chmod +x ~/ibc/*.sh
chmod +x ~/ibc/scripts/*.sh

echo "=== Creating IBC config ==="
mkdir -p ~/ibc
cat > ~/ibc/config.ini << 'IBCCONFIG'
# IBC Configuration
IbLoginId=kittureddy2000@gmail.com
IbPassword=
FIX=no
TradingMode=paper
AcceptIncomingConnectionAction=accept
AcceptNonBrokerageAccountWarning=yes
AcceptCredentialsExpiredWarning=yes
DismissPasswordExpiryWarning=yes
DismissNSEComplianceNotice=yes
AllowBlindTrading=yes
ReadOnlyApi=no
IBCCONFIG

echo ""
echo "=== Configuration created ==="
echo "IMPORTANT: You need to manually set your password in ~/ibc/config.ini"
echo ""
echo "=== Creating systemd service ==="
sudo tee /etc/systemd/system/ibgateway.service << EOF
[Unit]
Description=IB Gateway
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/ibc
ExecStart=/home/$USER/ibc/gatewaystart.sh
Restart=always
RestartSec=30
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ibgateway

echo ""
echo "=== Installation complete! ==="
echo "Next steps:"
echo "1. Edit ~/ibc/config.ini and add your IBKR password"
echo "2. Run: sudo systemctl start ibgateway"
