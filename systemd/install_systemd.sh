#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( dirname "$DIR" )"

echo "=== BTC Quantum Intelligence Systemd Service Installer ==="
echo ""
echo "To install as Linux systemd services that auto-start on boot:"
echo ""
echo "  sudo cp $DIR/btc-quantum-backend.service /etc/systemd/system/"
echo "  sudo cp $DIR/btc-quantum-frontend.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now btc-quantum-backend btc-quantum-frontend"
echo ""
echo "To monitor status:"
echo "  sudo systemctl status btc-quantum-backend"
echo "  sudo systemctl status btc-quantum-frontend"
echo ""
echo "To inspect logs:"
echo "  journalctl -u btc-quantum-backend -f"
echo "  journalctl -u btc-quantum-frontend -f"
