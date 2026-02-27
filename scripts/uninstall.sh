#!/bin/bash
# MLX Cockpit — Uninstaller
# Restores original server files from backups and removes installed artifacts

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}  MLX Cockpit Uninstaller${NC}"
echo ""

restored=0

# --- Restore mlx_lm server.py ---
MLX_LM_SERVER=$(python3 -c "import mlx_lm; import os; print(os.path.join(os.path.dirname(mlx_lm.__file__), 'server.py'))" 2>/dev/null || echo "")
if [ -n "$MLX_LM_SERVER" ] && [ -f "${MLX_LM_SERVER}.bak" ]; then
  echo -e "${BOLD}Restoring mlx_lm server...${NC}"
  cp "${MLX_LM_SERVER}.bak" "$MLX_LM_SERVER"
  rm "${MLX_LM_SERVER}.bak"
  echo -e "${GREEN}Restored: $MLX_LM_SERVER${NC}"
  restored=$((restored + 1))
elif [ -n "$MLX_LM_SERVER" ]; then
  echo -e "${YELLOW}No backup found for mlx_lm — skipping.${NC}"
fi

# --- Restore mlx_vlm server.py ---
MLX_VLM_SERVER=$(python3 -c "import mlx_vlm; import os; print(os.path.join(os.path.dirname(mlx_vlm.__file__), 'server.py'))" 2>/dev/null || echo "")
if [ -n "$MLX_VLM_SERVER" ] && [ -f "${MLX_VLM_SERVER}.bak" ]; then
  echo -e "${BOLD}Restoring mlx_vlm server...${NC}"
  cp "${MLX_VLM_SERVER}.bak" "$MLX_VLM_SERVER"
  rm "${MLX_VLM_SERVER}.bak"
  echo -e "${GREEN}Restored: $MLX_VLM_SERVER${NC}"
  restored=$((restored + 1))
elif [ -n "$MLX_VLM_SERVER" ]; then
  echo -e "${YELLOW}No backup found for mlx_vlm — skipping.${NC}"
fi

# --- Remove scan script ---
if [ -d "$HOME/.mlx-cockpit" ]; then
  echo -e "${BOLD}Removing ~/.mlx-cockpit/...${NC}"
  rm -rf "$HOME/.mlx-cockpit"
  echo -e "${GREEN}Removed.${NC}"
  restored=$((restored + 1))
fi

# --- Remove Übersicht widget ---
WIDGET_FILE="$HOME/Library/Application Support/Übersicht/widgets/mlx-cockpit.widget.jsx"
if [ -f "$WIDGET_FILE" ]; then
  echo -e "${BOLD}Removing Übersicht widget...${NC}"
  rm "$WIDGET_FILE"
  echo -e "${GREEN}Removed.${NC}"
  restored=$((restored + 1))
fi

echo ""
if [ $restored -gt 0 ]; then
  echo -e "${GREEN}${BOLD}Uninstall complete.${NC}"
  echo -e "  Restart any running MLX servers to use the original (unpatched) code."
else
  echo -e "${YELLOW}Nothing to uninstall — no artifacts found.${NC}"
fi
echo ""
