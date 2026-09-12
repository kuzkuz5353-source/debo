#!/bin/bash
# Archiso hook: SquashFS olusturulmadan once calisir
# Hiroki OS artik tek masaustu sunar: NEOX (Hyprland tabanli, Wayland).
# KDE Plasma, LXQt, XFCE, GNOME, Cinnamon, MATE, Budgie, i3wm, Openbox ve
# Calamares kaldirilmistir. Canli oturum ve kurulu sistem NEOX + hiroki-dm
# uzerinden calisir.

# Live kullanici olustur
useradd -m -G wheel,video,audio,storage,network,users,lp,scanner,uucp -s /bin/bash live 2>/dev/null || true

# Sifre ayarla
passwd --delete live 2>/dev/null || true
echo "live:live" | chpasswd

# Home izinleri
chown -R live:live /home/live
chmod 700 /home/live

# Home dizinine tum skel dosyalarini kopyala
cp -a /etc/skel/. /home/live/ 2>/dev/null || true
# Tum alt dizinleri olustur
mkdir -p /home/live/{Documents,Downloads,Music,Pictures,Videos,Templates,Public} 2>/dev/null || true
# Wallpapers symlink'lerini kopyala (symlink olarak kalsin)
for f in /usr/share/hiroki/wallpapers/*; do
  ln -sf "$f" "/home/live/Pictures/$(basename "$f")" 2>/dev/null || true
done
# NEOX/Hyprland config, mimeapps, gtk-3.0 config kopyala
cp -a /etc/skel/.config/mimeapps.list /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.config/gtk-3.0 /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.config/hypr /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.config/rofi /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.config/waybar /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.config/wofi /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.config/mako /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.config/picom /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.gtkrc-2.0 /home/live/ 2>/dev/null || true
cp -a /etc/skel/.config/user-dirs.dirs /home/live/.config/ 2>/dev/null || true
cp -a /etc/skel/.local /home/live/ 2>/dev/null || true
chmod 644 /home/live/.bash_profile 2>/dev/null || true
chown -R live:live /home/live

# /tmp izni
chmod 1777 /tmp

# D-Bus
dbus-uuidgen --ensure=/etc/machine-id 2>/dev/null || true

# Installer izni
chmod 755 /usr/bin/hiroki-installer 2>/dev/null || true

# glycin SVG loader bwrap sandbox live ortamda calismiyor
# Sadece sorunlu loader'lari ve icon temasini kaldir
rm -rf /usr/lib/glycin-loaders 2>/dev/null || true
pacman -Rns --noconfirm elementary-icon-theme 2>/dev/null || true
gdk-pixbuf-query-loaders --update-cache 2>/dev/null || true

# GTK3 varsayilan icon theme (SVG-crash olmasin)
mkdir -p /etc/gtk-3.0
cat > /etc/gtk-3.0/settings.ini <<'GTKEOF'
[Settings]
gtk-icon-theme-name=Adwaita
gtk-theme-name=Adwaita
GTKEOF

# glycin sandbox devre disi - tum oturumlarda
cat >> /home/live/.bash_profile <<'BASHEOF'
export GDK_DISABLE_SANDBOXED_LOADER=1
BASHEOF

# NetworkManager
systemctl enable NetworkManager.service 2>/dev/null || true
systemctl enable NetworkManager-wait-online.service 2>/dev/null || true
systemctl enable sshd.service 2>/dev/null || true

# --- Display Manager: hiroki-dm (Wayland, NEOX) ---
systemctl enable hiroki-dm.service 2>/dev/null || true
systemctl set-default graphical.target 2>/dev/null || true
mkdir -p /etc/hiroki
echo "neox" > /etc/hiroki/selected-de 2>/dev/null || true

# --- Hiroki OS Branding: tum Arch yazilarini Hiroki yap ---
# os-release
rm -f /etc/os-release /usr/lib/os-release 2>/dev/null || true
cat > /etc/os-release << 'OSREL'
NAME="Hiroki OS"
PRETTY_NAME="Hiroki OS 1.0 (Neox)"
ID=hiroki
ID_LIKE=arch
BUILD_ID=rolling
VERSION="1.0 Neox"
VERSION_ID="1.0"
HOME_URL="https://hiroki.os"
BUG_REPORT_URL="https://hiroki.os/issues"
LOGO=hiroki-neox-logo
OSREL
# lsb-release
rm -f /etc/lsb-release 2>/dev/null || true
cat > /etc/lsb-release << 'LSB'
DISTRIB_ID=Hiroki
DISTRIB_RELEASE=1.0
DISTRIB_CODENAME=Neox
DISTRIB_DESCRIPTION="Hiroki OS 1.0 Neox"
LSB

# Local pacman repo ekle (kurulumda paketler internetten inmesin)
if [ -f /usr/share/hiroki/cache/hiroki-local.db ]; then
  cat >> /etc/pacman.conf << 'REPO'

[hiroki-local]
SigLevel = Optional TrustAll
Server = file:///usr/share/hiroki/cache
REPO
  echo "Local repo eklendi: /etc/pacman.conf"
fi

# Kernel + initramfs + GRUB kur (Docker post-install hook'lari calismiyor)
# vmlinuzu modules dizininden /boot'a kopyala
if [ -d /usr/lib/modules ]; then
  _vm=$(find /usr/lib/modules -name 'vmlinuz' -type f 2>/dev/null | head -1)
  if [ -n "$_vm" ]; then
    cp "$_vm" /boot/vmlinuz-linux
    echo "vmlinuz kopyalandi: $_vm"
  fi
fi
# preset dosyasini her zaman olustur (mevcut olsa bile uzerine yaz)
if [ -f /boot/vmlinuz-linux ]; then
  cat > /etc/mkinitcpio.d/linux.preset << PRESET
ALL_kver=/boot/vmlinuz-linux
PRESETS=('default' 'fallback')
default_image=/boot/initramfs-linux.img
fallback_image=/boot/initramfs-linux-fallback.img
fallback_options="-S autodetect"
PRESET
  echo "mkinitcpio preset yazildi"
fi
# initramfs olustur (proc/dev/sys mount gerekli)
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sys /sys 2>/dev/null || true
mount --bind /dev /dev 2>/dev/null || true
mount --bind /dev/pts /dev/pts 2>/dev/null || true
mount --bind /dev/shm /dev/shm 2>/dev/null || true
echo "mount tamam, mkinitcpio baslatiliyor..."
mkinitcpio -P 2>&1 || true
echo "mkinitcpio tamamlandi"
umount /dev/shm /dev/pts /dev /sys /proc 2>/dev/null || true
# GRUB kur
if [ -f /boot/vmlinuz-linux ]; then
  mkdir -p /boot/grub
  grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=HIROKI --recheck 2>&1 || true
  grub-mkconfig -o /boot/grub/grub.cfg 2>&1 || true
  echo "GRUB kuruldu"
fi

# prison paketi Docker'da hook hatasi veriyor - IgnorePkg'a ekle
sed -i '/\[options\]/a IgnorePkg = prison' /etc/pacman.conf 2>/dev/null || true

# --- NEOX masaustu (Hyprland tabanli, tek masaustu) kurulumu ---
# Canli ISO'da da NEOX'un hazir olmasi icin scripts/install.sh ile /usr altina kurulur.
if [ -x /usr/share/neox-desktop/scripts/install.sh ]; then
  echo "NEOX masaustu kuruluyor..."
  PREFIX=/usr DESTDIR="" bash /usr/share/neox-desktop/scripts/install.sh 2>&1 || \
    echo "[Uyari] NEOX install.sh basarisiz (live ortam), kurulumda tekrar denenir"
  echo "NEOX kurulumu tamamlandi"
fi
