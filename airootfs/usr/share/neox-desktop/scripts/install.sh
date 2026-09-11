#!/usr/bin/env bash
# Install NEOX desktop files into a Linux system.
# The script is intentionally distro-aware but conservative: it explains missing
# packages and installs them only when a supported package manager is detected.
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${PREFIX:-/usr}"
DESTDIR="${DESTDIR:-}"
BIN_DIR="$DESTDIR$PREFIX/bin"
SHARE_DIR="$DESTDIR$PREFIX/share"
LIB_DIR="$DESTDIR$PREFIX/lib/neox-desktop"
DOC_DIR="$DESTDIR$PREFIX/share/doc/neox-desktop"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/neox"
HYPR_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/hypr"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

log() { printf '\033[1;34m[NEOX]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[NEOX WARN]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[NEOX ERROR]\033[0m %s\n' "$*" >&2; exit 1; }
need_root_for_system() {
    [[ -w "$DESTDIR$PREFIX" ]] && return 0
    [[ "${EUID:-$(id -u)}" -eq 0 ]] && return 0
    command -v sudo >/dev/null 2>&1 || fail "System install needs root or sudo."
}
run_root() {
    if [[ "${EUID:-$(id -u)}" -eq 0 || -n "$DESTDIR" || -w "$DESTDIR$PREFIX" ]]; then
        "$@"
    else
        sudo "$@"
    fi
}
install_file() {
    local mode="$1" src="$2" dst="$3"
    run_root install -Dm"$mode" "$src" "$dst"
}
copy_tree() {
    local src="$1" dst="$2"
    run_root mkdir -p "$dst"
    if [[ -d "$src" ]]; then
        (cd "$src" && tar cf - .) | (cd "$dst" && run_root tar xpf -)
    fi
}

check_dependencies() {
    local missing=()
    local commands=(Hyprland python3 grim slurp wl-copy brightnessctl playerctl nmcli bluetoothctl wpctl hyprpaper swayidle jq)
    for cmd in "${commands[@]}"; do
        command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
    done
    if (( ${#missing[@]} == 0 )); then
        log "All command dependencies are present."
        return 0
    fi
    warn "Missing command dependencies: ${missing[*]}"
    if command -v pacman >/dev/null 2>&1; then
        warn "Arch install example: sudo pacman -S hyprland python python-gobject gtk4 gtk4-layer-shell grim slurp wl-clipboard cliphist brightnessctl playerctl networkmanager bluez pipewire wireplumber polkit hyprpaper swayidle jq imagemagick"
    elif command -v apt-get >/dev/null 2>&1; then
        warn "Debian/Ubuntu install example: sudo apt install hyprland python3 python3-gi python3-cairo gir1.2-gtk-4.0 grim slurp wl-clipboard brightnessctl playerctl network-manager bluez pipewire wireplumber policykit-1 swayidle jq imagemagick"
    elif command -v dnf >/dev/null 2>&1; then
        warn "Fedora install example: sudo dnf install hyprland python3-gobject gtk4 grim slurp wl-clipboard brightnessctl playerctl NetworkManager bluez pipewire wireplumber polkit hyprpaper swayidle jq ImageMagick"
    fi
}

install_python_scripts() {
    log "Installing Python modules and executable wrappers."
    install_file 0755 "$PROJECT_ROOT/scripts/neox-session.sh" "$BIN_DIR/neox-session"
    install_file 0755 "$PROJECT_ROOT/scripts/neox-autostart.sh" "$BIN_DIR/neox-autostart"
    run_root install -d "$LIB_DIR/shell" "$LIB_DIR/widgets" "$LIB_DIR/themes" "$LIB_DIR/dbus"
    run_root cp -a "$PROJECT_ROOT/shell/." "$LIB_DIR/shell/"
    run_root cp -a "$PROJECT_ROOT/widgets/." "$LIB_DIR/widgets/"
    run_root cp -a "$PROJECT_ROOT/themes/." "$LIB_DIR/themes/"
    run_root cp -a "$PROJECT_ROOT/dbus/." "$LIB_DIR/dbus/"

    local scripts=(
        neox-shell neox-panel neox-desktop-grid neox-app-search neox-task-switcher
        neox-hd-dashboard neox-program-center
        neox-notification-center neox-control-center neox-lock-screen
        neox-logout-screen neox-wallpaper-manager neox-file-manager-integration
        neox-volume-brightness neox-clock-widget neox-weather-widget
        neox-system-monitor-widget neox-calendar-widget neox-media-player-widget
        neox-theme-engine
    )
    for script in "${scripts[@]}"; do
        local target="$BIN_DIR/$script"
        run_root install -d "$(dirname "$target")"
        case "$script" in
            neox-theme-engine)
                run_root tee "$target" >/dev/null <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$LIB_DIR/shell:\${PYTHONPATH:-}"
exec python3 "$LIB_DIR/themes/theme-engine.py" "\$@"
EOF
                ;;
            neox-clock-widget|neox-weather-widget|neox-system-monitor-widget|neox-calendar-widget|neox-media-player-widget)
                local py="$LIB_DIR/widgets/$script.py"
                run_root tee "$target" >/dev/null <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$LIB_DIR/shell:\${PYTHONPATH:-}"
exec python3 "$py" "\$@"
EOF
                ;;
            *)
                local py="$LIB_DIR/shell/$script.py"
                run_root tee "$target" >/dev/null <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$LIB_DIR/shell:\${PYTHONPATH:-}"
exec python3 "$py" "\$@"
EOF
                ;;
        esac
        run_root chmod 0755 "$target"
    done
}

install_configs() {
    log "Installing session, compositor, theme and config files."
    install_file 0644 "$PROJECT_ROOT/session/neox.desktop" "$SHARE_DIR/wayland-sessions/neox.desktop"
    install_file 0644 "$PROJECT_ROOT/session/neox-session.session" "$SHARE_DIR/neox/neox-session.session"
    install_file 0644 "$PROJECT_ROOT/compositor/hyprland.conf" "$SHARE_DIR/neox/hyprland.conf"
    run_root install -d "$SHARE_DIR/neox/themes" "$SHARE_DIR/neox/assets"
    run_root cp -a "$PROJECT_ROOT/themes/"*.css "$SHARE_DIR/neox/themes/"
    run_root cp -a "$PROJECT_ROOT/assets/." "$SHARE_DIR/neox/assets/"
    run_root install -d "$DOC_DIR"
    install_file 0644 "$PROJECT_ROOT/README.md" "$DOC_DIR/README.md"
    install_file 0644 "$PROJECT_ROOT/LICENSE" "$DOC_DIR/LICENSE"

    mkdir -p "$CONFIG_DIR" "$HYPR_DIR" "$CONFIG_DIR/wallpapers"
    cp -n "$PROJECT_ROOT/config/neox.conf" "$CONFIG_DIR/neox.conf"
    cp -n "$PROJECT_ROOT/config/keybindings.conf" "$CONFIG_DIR/keybindings.conf"
    cp -n "$PROJECT_ROOT/config/autostart.conf" "$CONFIG_DIR/autostart.conf"
    cp -n "$PROJECT_ROOT/config/gestures.conf" "$CONFIG_DIR/gestures.conf"
    cp -n "$PROJECT_ROOT/compositor/hyprland.conf" "$HYPR_DIR/hyprland.conf"
    cp -n "$PROJECT_ROOT/assets/wallpapers/default.svg" "$CONFIG_DIR/wallpapers/default.svg" || true
}

install_systemd() {
    log "Installing user systemd units."
    mkdir -p "$SYSTEMD_USER_DIR"
    cp "$PROJECT_ROOT/systemd/neox-shell.service" "$SYSTEMD_USER_DIR/neox-shell.service"
    cp "$PROJECT_ROOT/systemd/neox-compositor.service" "$SYSTEMD_USER_DIR/neox-compositor.service"
    systemctl --user daemon-reload || warn "systemctl --user daemon-reload failed; run it after login."
    systemctl --user enable neox-shell.service || warn "Could not enable neox-shell.service now."
}

main() {
    need_root_for_system
    check_dependencies || true
    install_python_scripts
    install_configs
    install_systemd
    log "NEOX installed. Select 'NEOX' in your display manager and log in."
}

main "$@"
