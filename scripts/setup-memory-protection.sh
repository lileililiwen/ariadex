#!/usr/bin/env bash
set -euo pipefail

# Add durable host protection for memory-heavy managed coding sessions.
# This script never disables existing swap and never exempts OpenCode from
# earlyoom; browsers are preferred victims so the host remains responsive.

readonly SWAPFILE=/swapfile-ariadex
readonly SWAPSIZE=8G
readonly FSTAB_ENTRY="$SWAPFILE none swap sw 0 0"

if ! swapon --show=NAME | grep -Fxq "$SWAPFILE"; then
    if [[ ! -e "$SWAPFILE" ]]; then
        sudo fallocate -l "$SWAPSIZE" "$SWAPFILE"
        sudo chmod 600 "$SWAPFILE"
        sudo mkswap "$SWAPFILE"
    fi
    sudo swapon "$SWAPFILE"
fi

if ! grep -Fqx "$FSTAB_ENTRY" /etc/fstab; then
    printf '%s\n' "$FSTAB_ENTRY" | sudo tee -a /etc/fstab >/dev/null
fi

sudo cp -n /etc/default/earlyoom /etc/default/earlyoom.bak 2>/dev/null || true
sudo sed -i '/^EARLYOOM_ARGS=/d' /etc/default/earlyoom
printf '%s\n' "EARLYOOM_ARGS=\"--prefer '^(chrome|chromium|firefox)$' -r 60\"" |
    sudo tee -a /etc/default/earlyoom >/dev/null
sudo systemctl enable --now earlyoom

printf '\nConfigured permanently:\n'
swapon --show
grep -F "$SWAPFILE" /etc/fstab
printf 'earlyoom: '
systemctl is-active earlyoom
