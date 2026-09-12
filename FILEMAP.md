# 🗂️ Hiroki OS Dosya Haritası — Tam Dizin Yapısı

Bu belge projenin **gerçek, çalışır** tüm dosyalarını listeler. Hiroki OS artık tek
masaüstü sunar: **NEOX** (Hyprland tabanlı, Wayland). KDE Plasma, LXQt, XFCE, GNOME,
Cinnamon, MATE, Budgie, i3wm, Openbox ve Calamares kaldırılmıştır.

```
hiroki-os/
├── profiledef.sh
├── packages.x86_64
├── pacman.conf
├── build.sh
├── README.md
├── BUILDING.md
├── INSTALL.md
├── CUSTOMIZATION.md
├── CONTRIBUTING.md
├── LICENSE
├── TESTING.md
├── FILEMAP.md (bu dosya)
│
├── efiboot/
│   ├── loader/loader.conf
│   └── loader/entries/hiroki.conf
├── syslinux/syslinux.cfg
├── grub/grub.cfg
│
├── neox-desktop/                        # NEOX masaüstü kaynak kodu (Hyprland tabanlı)
│   ├── compositor/hyprland.conf
│   ├── config/{neox.conf,keybindings.conf,autostart.conf,gestures.conf}
│   ├── shell/*.py                       # panel, arama, görev değiştirici, kontrol merkezi...
│   ├── widgets/*.py                     # saat, hava durumu, sistem izleme, medya oynatıcı
│   ├── themes/*.css + theme-engine.py
│   ├── dbus/neox-dbus-service.py
│   ├── systemd/{neox-shell.service,neox-compositor.service}
│   ├── session/{neox.desktop,neox-session.session}
│   ├── scripts/{install.sh,uninstall.sh,neox-session.sh,neox-autostart.sh}
│   └── packaging/{arch,deb,rpm}/
│
└── airootfs/
    ├── etc/
    │   ├── hostname                     # hiroki
    │   ├── locale.conf                  # LANG=tr_TR.UTF-8
    │   ├── locale.gen
    │   ├── vconsole.conf                # KEYMAP=trq
    │   ├── os-release                   # Hiroki OS 1.0 Neox
    │   ├── lsb-release
    │   ├── pacman.d/mirrorlist
    │   ├── sudoers.d/10-hiroki-live
    │   ├── skel/
    │   │   ├── .bashrc                  # Hiroki prompt + fastfetch
    │   │   ├── Pictures/wallpaper.jpg   # neox-gradient
    │   │   └── .config/
    │   │       ├── autostart/hiroki-welcome.desktop
    │   │       ├── gtk-3.0/{settings.ini,gtk.css}
    │   │       ├── hypr/hyprpaper.conf  # Hyprland/NEOX varsayılan yapılandırması
    │   │       ├── rofi/config.rasi     # Uygulama başlatıcı
    │   │       ├── waybar/{config,style.css}
    │   │       ├── wofi/hiroki.css
    │   │       ├── mako/config
    │   │       ├── picom/picom.conf
    │   │       ├── dunst/dunstrc
    │   │       ├── mimeapps.list
    │   │       └── fastfetch/config.jsonc
    │   ├── hiroki/
    │   │   ├── hiroki-dm.conf           # hiroki-dm görüntü yöneticisi yapılandırması
    │   │   ├── selected-de              # "neox" (tek değer)
    │   │   └── snapshot-settings.json
    │   └── systemd/system/
    │       ├── hiroki-dm.service        # NEOX/Wayland görüntü yöneticisi (getty@tty1 yerine)
    │       ├── hiroki-live.service
    │       ├── hiroki-boot-snapshot.{service,timer}
    │       └── hiroki-hello-update.{service,timer}
    ├── usr/
    │   ├── bin/
    │   │   ├── hiroki-hw-detect         # Bash - donanım algılama (NEOX min. gereksinim kontrolü)
    │   │   ├── hiroki-dm                # Bash - NEOX/Wayland görüntü yöneticisi (root)
    │   │   ├── hiroki-dm-session        # Bash - kullanıcı oturumu başlatıcı (neox-session çağırır)
    │   │   ├── hiroki-dm-wrapper        # Bash - D-Bus/XDG_RUNTIME_DIR hazırlayıp hiroki-dm'i çağırır
    │   │   ├── hiroki-installer         # PyQt6 - Hiroki'nin kendi grafik kurulum sihirbazı
    │   │   ├── hiroki-installer-launch  # Bash - sudo ile hiroki-installer'ı başlatır
    │   │   ├── hiroki-welcome           # Wrapper → Python GTK
    │   │   ├── hiroki-theme-manager     # Python GTK - tema/vurgu/duvar kağıdı
    │   │   ├── hiroki-wallpaper         # PyQt6 - duvar kağıdı seçici (hyprpaper IPC)
    │   │   ├── hiroki-tweaks            # Python - sistem ince ayarları
    │   │   ├── hiroki-neofetch          # Python - sistem bilgisi (NEOX/Hyprland farkında)
    │   │   ├── hiroki-update            # Python GTK + VTE
    │   │   ├── hiroki-btrfs-assistant   # PyQt6 - otomatik snapshot + GRUB restore
    │   │   ├── hiroki-driver-manager    # Python GTK
    │   │   ├── hiroki-network-manager   # PyQt6 - tek tıkla DNS + izole ağ
    │   │   ├── hiroki-kernel-manager    # PyQt6 - oyun çekirdeği yöneticisi
    │   │   ├── hiroki-hello-update      # PyQt6 - oyun kütüphane/sürücü otomasyonu
    │   │   └── hiroki-live-setup        # Bash - live hazırlık
    │   ├── share/
    │   │   ├── hiroki/
    │   │   │   └── wallpapers/5x.jpg + hiroki-neox-logo.png
    │   │   ├── hiroki-welcome/hiroki-welcome.py       # Hoş geldiniz (live/ilk boot)
    │   │   ├── themes/Hiroki-Dark/{gtk-3.0/gtk.css,gtk-4.0/gtk.css,index.theme}
    │   │   ├── icons/Hiroki-Icons/index.theme
    │   │   ├── backgrounds/neox/ (5 duvar kağıdı)
    │   │   ├── grub/themes/hiroki/theme.txt + background.png
    │   │   ├── plymouth/themes/hiroki/{hiroki.plymouth,hiroki.script}
    │   │   ├── hiroki/neofetch/config.conf
    │   │   ├── neox-desktop/                          # NEOX kaynak paketinin canlı ortam kopyası
    │   │   │   ├── scripts/install.sh                 # Hedef sisteme kurar (hiroki-installer çağırır)
    │   │   │   ├── compositor/hyprland.conf
    │   │   │   ├── shell/*.py, widgets/*.py, themes/*.css
    │   │   │   └── session/{neox.desktop,neox-session.session}
    │   │   └── applications/hiroki-*.desktop
    │   └── lib/systemd/user/ (neox-shell.service, neox-compositor.service kurulum sırasında eklenir)
    └── root/customize_airootfs.sh (archiso hook: live kullanıcı, NEOX/hiroki-dm kurulumu)
```

### Kritik Dosya Amaçları

| Dosya | Amaç |
|---|---|
| `hiroki-hw-detect` | RAM/CPU/GPU/disk/virt algılar, NEOX'un 4 GB önerisiyle karşılaştırır → `/tmp/hiroki-hw-info.json` |
| `hiroki-dm` + `hiroki-dm-wrapper` + `hiroki-dm-session` | Hiroki'nin kendi Wayland görüntü yöneticisi; tty1'de systemd servisi olarak çalışır, `neox-session`'ı başlatır |
| `hiroki-installer` | PyQt6 tabanlı kurulum sihirbazı: disk seçimi, kullanıcı, dil/klavye/saat dilimi, Btrfs/ext4, NEOX kurulumu, GRUB |
| `hiroki-welcome.py` | Live: Hiroki Installer'ı başlat; Kurulu: Güncelle + Tema + araçlar |
| `neox-desktop/scripts/install.sh` | NEOX'u `/usr`, `~/.config/hypr`, `~/.config/neox` altına kurar; `hiroki-installer` tarafından çağrılır |
| `profiledef.sh` | `HIROKI_OS` etiketi, `hiroki-os` ismi, file_permissions executable |
| `build.sh` | ISO derleme, checksum, QEMU talimatı |

Tüm dosyalar POSIX/Bash/Python3/GTK3/Systemd resmi dokümantasyonuyla uyumludur.
