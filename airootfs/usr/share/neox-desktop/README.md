# NEOX Desktop

NEOX, Hyprland Wayland compositor üzerine inşa edilmiş, mobil işletim sistemi estetiğine sahip deneysel bir masaüstü ortamıdır.  Bu kaynak ağacı Python 3.11+, GTK4, gtk4-layer-shell, Hyprland IPC, D-Bus ve standart Wayland yardımcı araçlarını kullanır.

> Durum: Deneysel prototipten ileri seviye HD arayüz tabanına yükseltildi.  Temel shell, launcher, Dynamic Island, task switcher, bildirim servisi, kontrol merkezi, OSD, duvar kağıdı yöneticisi, widget'lar, HD Dashboard ve Program Center gerçek çalıştırılabilir kod olarak sağlanır.  Dağıtım paketlemesi için Arch PKGBUILD ve Debian/RPM talimatları eklenmiştir.

## Bileşenler

| Yol | Açıklama |
| --- | --- |
| `compositor/hyprland.conf` | NEOX için Hyprland ana konfigürasyonu: monitör, giriş, tema, animasyon, layerrule, tuşlar, autostart. |
| `shell/neox_common.py` | Paylaşılan runtime: logging, config, desktop-entry scanner/cache, fuzzy search, Hyprland IPC, Unix event bus. |
| `shell/neox_hd_ui.py` | HD tasarım sistemi: adaptive scale, cam yüzeyler, metric kartları ve ortak GTK CSS token'ları. |
| `shell/neox-shell.py` | Ana daemon: event bus, autostart, app index, Hyprland event mirror, update check. |
| `shell/neox-panel.py` | Dynamic Island panel: saat/tarih, arama modu, medya modu, durum göstergeleri. |
| `shell/neox-desktop-grid.py` | Mobil launcher: .desktop tarama, 8x5 sayfalama, hover/click efektleri, DnD, klasör, kategori modu. |
| `shell/neox-app-search.py` | Bağımsız arama overlay'i ve CLI fallback. |
| `shell/neox-hd-dashboard.py` | HD ana yüzey: hero saat, arama, favori programlar, sistem metrikleri, workspace ve hızlı eylemler. |
| `shell/neox-program-center.py` | İleri seviye program merkezi: kategori, arama, favori, launch, Flatpak/Snap kaldırma, update sayacı. |
| `shell/neox-task-switcher.py` | Super görev değiştirici: Hyprland clients, sayfalı önizleme kartları, focus/close/workspace taşıma. |
| `shell/neox-notification-center.py` | `org.freedesktop.Notifications` D-Bus daemon'u ve bildirim merkezi UI. |
| `shell/neox-control-center.py` | Hızlı ayarlar ve tam ayarlar penceresi. |
| `shell/neox-lock-screen.py` | Güvenli `swaylock` tabanlı kilit ekranı wrapper'ı. |
| `shell/neox-logout-screen.py` | Kapat/yeniden başlat/uyut/oturum kapat ekranı. |
| `shell/neox-wallpaper-manager.py` | Hyprpaper/swaybg/mpvpaper duvar kağıdı yöneticisi, slideshow, accent çıkarımı. |
| `shell/neox-file-manager-integration.py` | Varsayılan dosya yöneticisi ve klasör açma entegrasyonu. |
| `shell/neox-volume-brightness.py` | PipeWire ses ve brightnessctl parlaklık OSD'si. |
| `widgets/*.py` | Saat, hava durumu, sistem monitörü, takvim ve medya oynatıcı widget'ları. |
| `themes/*.css` | Koyu, açık ve Nord tema değişkenleri. |
| `themes/theme-engine.py` | Tema uygulama, GTK settings ve otomatik tema motoru. |
| `config/*.conf` | Kullanıcı yapılandırmaları: ana config, keybindings, autostart, gestures. |
| `scripts/*.sh` | Kurulum, kaldırma, session ve autostart betikleri. |
| `dbus/*` | `org.neox.Shell` D-Bus köprüsü ve policy dosyası. |
| `session/*` | Display manager Wayland session girdileri. |
| `systemd/*` | Kullanıcı systemd unit dosyaları. |
| `packaging/*` | Arch PKGBUILD ve Debian/RPM paketleme notları. |

## Sistem bağımlılıkları

- Hyprland
- Python 3.11+
- python3-gi, python3-cairo, GTK4, gtk4-layer-shell
- grim, slurp, wl-clipboard, cliphist
- brightnessctl, playerctl
- NetworkManager, BlueZ
- pipewire, wireplumber
- polkit agent
- hyprpaper veya swaybg
- swayidle, swaylock
- jq, ImageMagick
- Opsiyonel: dbus-next, Pillow, psutil, watchdog, wf-recorder, mpvpaper

## Kurulum

```bash
cd neox-desktop
make check
sudo make install
```

Ardından display manager ekranında **NEOX** oturumunu seçin.

Geliştirme ağacından test etmek için:

```bash
export PYTHONPATH="$PWD/shell:$PYTHONPATH"
python3 shell/neox-shell.py --reload-apps
python3 shell/neox-app-search.py --cli firefox
```

## Tuşlar

- `Super`: görev değiştirici
- `Super+Space`: arama
- `Super+Q`: aktif pencereyi kapat
- `Super+F`: fullscreen
- `Super+T`: terminal
- `Super+E`: dosya yöneticisi
- `Super+L`: kilit ekranı
- `Super+C`: kontrol merkezi
- `Super+H`: HD Dashboard
- `Super+A`: Program Center
- `Super+D`: desktop grid
- `Print`, `Super+Print`, `Super+Shift+Print`: ekran görüntüsü
- Ses/parlaklık donanım tuşları: OSD ile kontrol

## Performans tasarımı

- `.desktop` tarama sonucu `~/.cache/neox/applications.json` içinde imza kontrollü cache olarak saklanır.
- Dosya sistemi değişiklikleri düşük maliyetli signature polling ile izlenir; `watchdog` kuruluysa genişletilebilir.
- Hyprland IPC çağrıları küçük zaman aşımlarıyla çalışır ve UI'yi kilitlememek için arka plan thread'leri kullanılır.
- UI bileşenleri singleton lock ile duplicate yüzeyleri engeller.

## Güvenlik notu

Kilit ekranı gerçek kimlik doğrulamayı `swaylock` üzerinden yapar.  Python ile özel PAM kilidi yazmak mümkün olsa da yanlış uygulanırsa oturumu güvensiz bırakabilir; bu nedenle NEOX güvenli varsayılan olarak swaylock kullanır.

## Lisans

GPL-3.0-or-later.  Tam lisans metni `LICENSE` dosyasındadır.
