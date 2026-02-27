#!/bin/bash
# MLX Cockpit — Installer
# Installs the Übersicht desktop widget and patches MLX servers with metrics endpoints

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}  ✈  MLX Cockpit Installer${NC}"
echo -e "  ${CYAN}Live performance monitoring for MLX inference servers${NC}"
echo ""

# --- Check prerequisites ---
if ! command -v python3 &>/dev/null; then
  echo -e "${YELLOW}Python 3 not found. Please install Python first.${NC}"
  exit 1
fi

# Find mlx_lm server.py
MLX_LM_SERVER=$(python3 -c "import mlx_lm; import os; print(os.path.join(os.path.dirname(mlx_lm.__file__), 'server.py'))" 2>/dev/null || echo "")
if [ -z "$MLX_LM_SERVER" ]; then
  echo -e "${YELLOW}mlx_lm not found. Install it first: pip install mlx-lm${NC}"
else
  echo -e "${GREEN}Found mlx_lm server:${NC} $MLX_LM_SERVER"
fi

# Find mlx_vlm server.py
MLX_VLM_SERVER=$(python3 -c "import mlx_vlm; import os; print(os.path.join(os.path.dirname(mlx_vlm.__file__), 'server.py'))" 2>/dev/null || echo "")
if [ -n "$MLX_VLM_SERVER" ]; then
  echo -e "${GREEN}Found mlx_vlm server:${NC} $MLX_VLM_SERVER"
else
  echo -e "${YELLOW}mlx_vlm not found (optional — vision model support).${NC}"
fi

# --- Patch mlx_lm ---
if [ -n "$MLX_LM_SERVER" ]; then
  echo ""
  echo -e "${BOLD}Patching mlx_lm server with metrics endpoints...${NC}"
  if grep -q "_metrics_store" "$MLX_LM_SERVER" 2>/dev/null; then
    echo -e "${GREEN}Already patched — skipping.${NC}"
  else
    python3 "$(dirname "$0")/patch_mlx_lm.py" "$MLX_LM_SERVER"
    echo -e "${GREEN}Patched successfully.${NC}"
  fi
fi

# --- Patch mlx_vlm ---
if [ -n "$MLX_VLM_SERVER" ]; then
  echo ""
  echo -e "${BOLD}Patching mlx_vlm server with metrics endpoints...${NC}"
  if grep -q "_vlm_metrics_store" "$MLX_VLM_SERVER" 2>/dev/null; then
    echo -e "${GREEN}Already patched — skipping.${NC}"
  else
    python3 "$(dirname "$0")/patch_mlx_vlm.py" "$MLX_VLM_SERVER"
    echo -e "${GREEN}Patched successfully.${NC}"
  fi
fi

# --- Install scan script ---
echo ""
echo -e "${BOLD}Installing scan script...${NC}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.mlx-cockpit"
cp "$SCRIPT_DIR/../widget/mlx-scan.sh" "$HOME/.mlx-cockpit/mlx-scan.sh"
chmod +x "$HOME/.mlx-cockpit/mlx-scan.sh"
echo -e "${GREEN}Scan script installed to ~/.mlx-cockpit/mlx-scan.sh${NC}"

# --- Install Übersicht widget ---
echo ""
WIDGET_DIR="$HOME/Library/Application Support/Übersicht/widgets"
if [ -d "$WIDGET_DIR" ]; then
  echo -e "${BOLD}Installing Übersicht widget...${NC}"
  # Copy widget and replace scan path placeholder with installed location
  sed "s|__MLX_SCAN_PATH__|$HOME/.mlx-cockpit/mlx-scan.sh|g" \
    "$SCRIPT_DIR/../widget/mlx-cockpit.widget.jsx" \
    > "$WIDGET_DIR/mlx-cockpit.widget.jsx"
  echo -e "${GREEN}Widget installed.${NC}"
else
  echo -e "${YELLOW}Übersicht not found. Install it from https://tracesof.net/uebersicht/${NC}"
  echo -e "${YELLOW}Or: brew install --cask ubersicht${NC}"
  echo -e "Then re-run this script to install the widget."
fi

echo ""
echo -e "${GREEN}${BOLD}Installation complete!${NC}"
echo ""
echo -e "  ${CYAN}Start your MLX servers (any port from 8080-8090):${NC}"
echo -e "    python -m mlx_lm.server --model <model> --port 8080"
echo -e "    python -m mlx_vlm.server --port 8081"
echo ""
echo -e "  ${CYAN}Auto-discovery:${NC} scans ports 8080-8090 for running MLX servers"
echo -e "  ${CYAN}Open dashboard:${NC} http://localhost:8080/dashboard"
echo -e "  ${CYAN}Desktop widget:${NC} auto-updates via Übersicht"
echo -e "  ${CYAN}Uninstall:${NC}      ./scripts/uninstall.sh"
echo ""
