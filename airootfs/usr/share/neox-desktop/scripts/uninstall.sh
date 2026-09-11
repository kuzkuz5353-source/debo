#!/usr/bin/env bash
# Remove system-installed NEOX files while preserving user configuration by
# default.  Pass --purge-user-config to remove ~/.config/neox as well.
set -Eeuo pipefail

PREFIX="${PREFIX:-/usr}"
DESTDIR="${DESTDIR:-}"
PURGE_USER_CONFIG="false"
[[ "${1:-}" == "--purge-user-config" ]] && PURGE_USER_CONFIG="true"

log() { printf '\033[1;34m[NEOX]\033[0m %s\n' "$*"; }
run_root() {
    if [[ "${EUID:-$(id -u)}" -eq 0 || -n "$DESTDIR" ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

systemctl --user disable --now neox-shell.service 2>/dev/null || true
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/neox-shell.service"
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/neox-compositor.service"
systemctl --user daemon-reload 2>/dev/null || true

for bin in neox-session neox-autostart neox-shell neox-panel neox-desktop-grid neox-app-search \
           neox-task-switcher neox-hd-dashboard neox-program-center \
           neox-notification-center neox-control-center neox-lock-screen neox-logout-screen \
           neox-wallpaper-manager neox-file-manager-integration neox-volume-brightness \
           neox-clock-widget neox-weather-widget neox-system-monitor-widget neox-calendar-widget \
           neox-media-player-widget neox-theme-engine; do
    run_root rm -f "$DESTDIR$PREFIX/bin/$bin"
done

run_root rm -rf "$DESTDIR$PREFIX/lib/neox-desktop"
run_root rm -rf "$DESTDIR$PREFIX/share/neox"
run_root rm -rf "$DESTDIR$PREFIX/share/doc/neox-desktop"
run_root rm -f "$DESTDIR$PREFIX/share/wayland-sessions/neox.desktop"

if [[ "$PURGE_USER_CONFIG" == "true" ]]; then
    rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/neox"
    log "User configuration removed."
else
    log "User configuration kept in ~/.config/neox."
fi
log "NEOX uninstalled."
