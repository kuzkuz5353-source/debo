#!/usr/bin/env bash
# Execute user-defined NEOX autostart entries.  Lines are shell commands;
# comments and empty lines are ignored.  Commands are started in the background.
set -Eeuo pipefail

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/neox/autostart.conf"
[[ -f "$CONFIG" ]] || exit 0

while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$line" ]] && continue
    bash -lc "$line" >/dev/null 2>&1 &
done < "$CONFIG"
