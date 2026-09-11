#!/usr/bin/env bash
# Hiroki OS - Servisleri Etkinleştir
set -euo pipefail
DE="${1:-xfce}"
echo "[Hiroki Servisler] DE: $DE"

# Temel servisler
systemctl enable NetworkManager.service 2>/dev/null || true
systemctl enable NetworkManager-dispatcher.service 2>/dev/null || true
systemctl enable bluetooth.service 2>/dev/null || true
systemctl enable cups.service 2>/dev/null || true
systemctl enable cups.socket 2>/dev/null || true
systemctl enable ufw.service 2>/dev/null || systemctl enable firewalld.service 2>/dev/null || true
systemctl enable fstrim.timer 2>/dev/null || true
systemctl enable reflector.timer 2>/dev/null || true

# Ses
systemctl --global enable pipewire.service 2>/dev/null || true
systemctl --global enable pipewire-pulse.service 2>/dev/null || true
systemctl --global enable wireplumber.service 2>/dev/null || true

# Zaman senkron
systemctl enable systemd-timesyncd.service 2>/dev/null || true

# Btrfs ise snapper/timeshift/grub-btrfs (Hiroki OS Btrfs Asistanı)
if findmnt -n -o FSTYPE / | grep -q btrfs; then
    systemctl enable snapper-timeline.timer 2>/dev/null || true
    systemctl enable snapper-cleanup.timer 2>/dev/null || true
    # grub-btrfsd, Timeshift snapshotlarini otomatik olarak GRUB menusune ekler
    mkdir -p /etc/default/grub-btrfs
    if [ -f /etc/default/grub-btrfs/config ]; then
        grep -q "^GRUB_BTRFS_LIMIT" /etc/default/grub-btrfs/config || echo 'GRUB_BTRFS_LIMIT="50"' >> /etc/default/grub-btrfs/config
        grep -q "^GRUB_BTRFS_SUBMENUNAME" /etc/default/grub-btrfs/config || echo 'GRUB_BTRFS_SUBMENUNAME="Hiroki OS Neox Snapshots"' >> /etc/default/grub-btrfs/config
    fi
    if [ -d /usr/lib/systemd/system ] && [ -f /usr/lib/systemd/system/grub-btrfsd.service ]; then
        mkdir -p /etc/systemd/system/grub-btrfsd.service.d
        cat > /etc/systemd/system/grub-btrfsd.service.d/hiroki-timeshift.conf << 'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/grub-btrfsd --syslog --timeshift-auto
EOF
        systemctl enable grub-btrfsd.service 2>/dev/null || true
    else
        systemctl enable grub-btrfs.path 2>/dev/null || true
    fi
    # Hiroki Btrfs Asistanı: pacman islemlerinden once otomatik snapshot
    # pacman hook uzerinden calisir (bkz. /etc/pacman.d/hooks/95-hiroki-btrfs-assistant.hook)
    # Acilis sonrasi 90sn snapshot secimi kullanicinin Btrfs Asistani panelinden acabilecegi bir secenektir.
fi

# Avahi (ağ keşfi)
systemctl enable avahi-daemon.service 2>/dev/null || true

# Hiroki OS Hello Update: oyun kutuphane/surucu otomatik tamamlama (arka plan)
systemctl enable hiroki-hello-update.timer 2>/dev/null || true

echo "[Hiroki Servisler] Tamamlandı"
