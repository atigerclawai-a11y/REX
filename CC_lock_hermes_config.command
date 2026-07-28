#!/bin/bash
chflags uchg ~/.hermes/profiles/cloud/config.yaml ~/.hermes/profiles/cloud/.env
echo "✓ config.yaml and .env are now locked (chflags uchg)"
echo "  hermes setup can no longer overwrite them."
echo "  To unlock later: chflags nouchg ~/.hermes/profiles/cloud/config.yaml ~/.hermes/profiles/cloud/.env"
echo ""
echo "Press any key to close..."
read -n 1
