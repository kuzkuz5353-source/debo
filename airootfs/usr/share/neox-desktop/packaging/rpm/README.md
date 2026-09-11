# Fedora/RPM packaging

Create an RPM spec that stages files with:

```bash
DESTDIR=%{buildroot} PREFIX=/usr bash scripts/install.sh
```

Runtime dependency list:

- hyprland
- python3-gobject, python3-cairo, gtk4, gtk4-layer-shell
- grim, slurp, wl-clipboard, brightnessctl, playerctl
- NetworkManager, bluez, pipewire, wireplumber, polkit
- hyprpaper or swaybg, swayidle, jq, ImageMagick

Optional: python3-dbus-next, python3-pillow, python3-psutil, wf-recorder,
mpvpaper, swaylock.
