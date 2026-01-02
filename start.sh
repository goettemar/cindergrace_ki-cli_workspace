#!/bin/bash
# KI-CLI Workspace Starter
# Erstellt venv bei Bedarf, installiert Dependencies und startet die App

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Farben für Output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🤖 KI-CLI Workspace${NC}"
echo "================================"

# Python prüfen
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 nicht gefunden"
    exit 1
fi

# venv erstellen falls nicht vorhanden
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}📦 Erstelle virtuelle Umgebung...${NC}"
    python3 -m venv .venv
fi

# venv aktivieren
source .venv/bin/activate

# Dependencies prüfen und installieren
if [ ! -f ".venv/.deps_installed" ] || [ "pyproject.toml" -nt ".venv/.deps_installed" ]; then
    echo -e "${YELLOW}📥 Installiere Dependencies...${NC}"
    pip install -q --upgrade pip
    pip install -q -e .
    touch .venv/.deps_installed
fi

echo -e "${GREEN}🚀 Starte App auf http://127.0.0.1:7870${NC}"
echo "================================"
python app.py
