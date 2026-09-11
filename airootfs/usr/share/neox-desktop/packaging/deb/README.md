# Debian/Ubuntu packaging

Build a `.deb` package with `dpkg-buildpackage` or `fpm`.

## Minimal fpm example

```bash
sudo apt install ruby ruby-dev build-essential
sudo gem install fpm
VERSION=0.1.0
fpm -s dir -t deb -n neox-desktop -v "$VERSION" \
  --license GPL-3.0-or-later \
  --description "Mobile-inspired Hyprland desktop environment shell" \
  --depends hyprland --depends python3 --depends python3-gi --depends python3-cairo \
  --depends gir1.2-gtk-4.0 --depends grim --depends slurp --depends wl-clipboard \
  --depends brightnessctl --depends playerctl --depends network-manager --depends bluez \
  --depends pipewire --depends wireplumber --depends policykit-1 --depends swayidle \
  --prefix /usr \
  neox-desktop/=/usr/share/src/neox-desktop
```

For production packaging, install files into a staged `debian/tmp` directory by
running `DESTDIR=$PWD/debian/tmp PREFIX=/usr bash scripts/install.sh` and define
Debian control metadata normally.
