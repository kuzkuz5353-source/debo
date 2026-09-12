# 🎨 Hiroki OS Özelleştirme Rehberi

NEOX temasını ve kendi Hiroki temanı nasıl oluşturacağını anlatır. Hiroki OS artık
tek masaüstü sunar: **NEOX** (Hyprland tabanlı, Wayland). Bu rehber yalnızca NEOX'a
özgü özelleştirmeleri kapsar.

---

## 1. Renk Paleti

| İsim | Kod | Kullanım |
|---|---|---|
| Koyu mor (primary) | `#2D1B69` | Başlıklar, panel, vurgu |
| Canlı pembe (secondary) | `#E91E8C` | Buton, seçili, link |
| Turkuaz (tertiary) | `#00D4AA` | İkincil vurgu, badge |
| Koyu arkaplan | `#0D0D1A` | Pencere arkaplanı |
| Açık koyu | `#1A1A2E` | Kartlar, menüler |
| Metin primary | `#EAEAEA` | Ana metin |
| Metin secondary | `#A0A0B8` | Açıklama |

---

## 2. Tema Yöneticisi (GUI)

```bash
hiroki-theme-manager
```

- **Tema:** `Hiroki-Dark` (varsayılan) / `Hiroki-Light`
- **Vurgu rengi:** Pembe / Mor / Turkuaz (`~/.config/hiroki/accent.conf`)
- **Duvar kağıdı:** 5 seçenek → `hyprctl hyprpaper` IPC ile anında uygulanır

Manüel:

```bash
# GTK (settings.ini üzerinden, Wayland/NEOX oturumunda anlık)
cat > ~/.config/gtk-3.0/settings.ini <<'EOF'
[Settings]
gtk-theme-name=Hiroki-Dark
gtk-icon-theme-name=Hiroki-Icons
EOF

# Duvar kağıdı (NEOX / hyprpaper)
hyprctl hyprpaper preload /usr/share/hiroki/wallpapers/minimal-mountain.jpg
hyprctl hyprpaper wallpaper ",/usr/share/hiroki/wallpapers/minimal-mountain.jpg"
```

Ya da doğrudan NEOX'un kendi motorunu kullanın:

```bash
neox-theme-engine neox-hd --accent '#E91E8C'
```

---

## 3. GTK Teması

Konum: `/usr/share/themes/Hiroki-Dark/`

- `gtk-3.0/gtk.css`
- `gtk-4.0/gtk.css`

Kendi varyantını oluştur:

```bash
sudo cp -r /usr/share/themes/Hiroki-Dark /usr/share/themes/Hiroki-My
sudo nano /usr/share/themes/Hiroki-My/gtk-3.0/gtk.css
# @define-color hiroki_pink #E91E8C; satırını değiştir
```

`~/.config/gtk-3.0/settings.ini` içindeki `gtk-theme-name` değerini `Hiroki-My` yapın.

---

## 4. İkon Teması

Konum: `/usr/share/icons/Hiroki-Icons/index.theme` — Papirus Dark miras, mor klasörler

Kendi ikonunu ekle:

```bash
mkdir -p ~/.local/share/icons/Hiroki-My/48x48/apps
cp my-icon.png ~/.local/share/icons/Hiroki-My/48x48/apps/
gtk-update-icon-cache ~/.local/share/icons/Hiroki-My
```

`~/.config/gtk-3.0/settings.ini` içindeki `gtk-icon-theme-name` değerini `Hiroki-My` yapın.

---

## 5. NEOX Masaüstü Özelleştirme

NEOX'un tüm yapılandırması `~/.config/neox/` ve `~/.config/hypr/hyprland.conf` altındadır.

### Hyprland (derleyici) ayarları
- `~/.config/hypr/hyprland.conf` — kaynak: `neox-desktop/compositor/hyprland.conf`
- Renk, border, blur, animasyon ayarları burada
- Değişikliklerden sonra: `hyprctl reload`

### NEOX kabuğu ayarları
- `~/.config/neox/neox.conf` — genel davranış
- `~/.config/neox/keybindings.conf` — kısayollar (kaynak dosyadan `source =` ile dahil edilir)
- `~/.config/neox/autostart.conf` — oturum açılışında çalışacak komutlar
- `~/.config/neox/gestures.conf` — dokunmatik/touchpad jestleri

### Panel araçları
- `rofi` (uygulama başlatıcı) → `~/.config/rofi/config.rasi`
- `waybar` (isteğe bağlı ek panel) → `~/.config/waybar/config` + `style.css`
- `wofi` (alternatif başlatıcı) → `~/.config/wofi/hiroki.css`
- `mako` / `dunst` (bildirim) → `~/.config/mako/config`, `~/.config/dunst/dunstrc`
- `picom` (X11 uygulamaları için opsiyonel compositor katmanı) → `~/.config/picom/picom.conf`

Kısayol rehberi ve tüm bağlamalar için: [`neox-desktop/config/keybindings.conf`](neox-desktop/config/keybindings.conf)

---

## 6. GRUB Teması

Konum: `/usr/share/grub/themes/hiroki/theme.txt`

Değiştir:
```bash
sudo nano /etc/default/grub
# GRUB_THEME="/usr/share/grub/themes/hiroki/theme.txt"
sudo grub-mkconfig -o /boot/grub/grub.cfg
```

Kendi arkaplanın:
```bash
sudo cp ~/resim.png /usr/share/grub/themes/hiroki/background.png
```

---

## 7. Plymouth (Açılış Animasyonu)

```bash
sudo plymouth-set-default-theme -R hiroki
# Test: sudo plymouthd; sudo plymouth --show-splash; sleep 5; sudo plymouth quit
```

Tema dosyaları: `/usr/share/plymouth/themes/hiroki/hiroki.script`

---

## 8. Neofetch / Fastfetch

```bash
fastfetch --logo /usr/share/hiroki/ascii/hiroki.txt
hiroki-neofetch
```

Yapılandırma:
- `~/.config/fastfetch/config.jsonc`

---

## 9. Kendi Temanı Oluştur ve Paketle

1. `hiroki-theme-my` klasörü oluştur
2. GTK, ikon, duvar kağıdı ve/veya `neox-desktop/themes/*.css` tabanlı NEOX teması ekle
3. `PKGBUILD` yaz (AUR örneği):
```bash
pkgname=hiroki-theme-my
pkgver=1.0
pkgrel=1
arch=('any')
source=("my-theme.tar.gz")
package() { cp -r usr "$pkgdir"/ }
```
4. `makepkg -si`

Topluluğa gönder: https://github.com/hiroki-os/hiroki-os/issues

---

## 10. Dosya Haritası

```
airootfs/usr/share/themes/Hiroki-Dark/          # GTK
airootfs/usr/share/icons/Hiroki-Icons/          # İkon
airootfs/usr/share/hiroki/wallpapers/5x.jpg     # Duvar kağıtları
airootfs/usr/share/grub/themes/hiroki/          # GRUB
airootfs/usr/share/plymouth/themes/hiroki/      # Plymouth
airootfs/usr/share/neox-desktop/                # NEOX kaynak ağacı (canlı ortamdaki kopya)
airootfs/etc/skel/.config/hypr/                 # Varsayılan Hyprland yapılandırması
airootfs/etc/skel/.config/{rofi,waybar,wofi,mako,dunst,picom}/  # NEOX panel araçları
airootfs/etc/skel/.config/gtk-3.0/settings.ini  # Varsayılan GTK
airootfs/etc/skel/.bashrc                       # Hiroki prompt + fastfetch
neox-desktop/                                   # NEOX masaüstü kaynak kodu
```

İyi özelleştirmeler! 🌸
