# 💿 Hiroki OS Kurulum Rehberi — Neox 1.0

Bu belge BIOS ve UEFI, disk bölümleme, dual-boot ve kurulum sonrası adımları kapsar.
Hiroki OS artık tek masaüstü sunar: **NEOX** (Hyprland tabanlı, Wayland). Kurulum
Calamares yerine kendi grafik sihirbazımız **Hiroki Installer** (PyQt6) ile yapılır.

---

## 1. Sistem Gereksinimleri

| Bileşen | Minimum | Önerilen |
|---|---|---|
| RAM | 2 GB | 4 GB+ (NEOX için önerilen) |
| Disk | 15 GB | 30 GB+ (Btrfs snapshot için 40 GB) |
| CPU | 1 GHz, 1 çekirdek | 2 GHz, 2+ çekirdek |
| GPU | Mesa destekli (KMS) | Vulkan destekli (AMD/Intel/NVIDIA) |
| Ortam | BIOS veya UEFI | UEFI + Secure Boot kapalı |

> `hiroki-hw-detect` kurulum öncesi donanımınızı analiz eder ve NEOX için yeterli olup
> olmadığını bildirir (kurulumu engellemez).

---

## 2. ISO'yu Hazırla

```bash
# İndir (yakında)
wget https://github.com/hiroki-os/hiroki-os/releases/download/v1.0/hiroki-os-1.0-x86_64.iso
sha256sum -c hiroki-os-*.iso.sha256

# USB'ye yaz (Linux)
lsblk
sudo dd if=hiroki-os-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
# Windows: Rufus (DD modu), Etcher, Ventoy
# macOS: Etcher veya dd
```

Secure Boot: Hiroki OS Secure Boot imzalı değildir; BIOS'ta **Secure Boot'u kapatın** veya `shim` kullanın.

---

## 3. Boot Menüsü

ISO açıldığında GRUB/slideshow:

- **Hiroki OS'u Dene** — NEOX live, otomatik giriş (`live` kullanıcısı, şifre yok)
- **Hiroki OS'u Kur** — Hiroki Installer'ı başlatır
- **Donanım Bilgisi** / **Bellek Testi**
- BIOS: Syslinux menüsü aynı seçenekleri sunar

Live masaüstünde:

- **Hiroki Hoş Geldiniz** otomatik açılır → **Hiroki Installer'ı Başlat** ile kuruluma geçin

İnternet: NEOX panelindeki ağ simgesi → Wi-Fi/Ethernet. Kurulum öncesi bağlanmanız önerilir (paketler için).

---

## 4. Hiroki Installer Adımları

Hiroki Installer tek pencereli bir sihirbazdır:

1. **Mod seç** — `wipe` (diski tamamen sil ve kur) veya `partition` (mevcut bölüme kur)
2. **Disk / bölüm seç**
3. **Kullanıcı adı, bilgisayar adı, parola**
4. **Dil / saat dilimi / klavye düzeni** (`tr_TR.UTF-8` / `en_US.UTF-8`, `Europe/Istanbul` / `UTC`, `trq` / `us`)
5. **Yeni Linux alanı (GiB)** — `partition` modunda kullanılmaz
6. **Önizleme ve onay** — Disk yazma işlemleri yalnızca burada verdiğiniz açık onaydan sonra başlar
7. **Kurulum** — Bölümleme, `pacstrap`, NEOX kurulumu, GRUB, `hiroki-dm` etkinleştirme
8. **Bitti** → Yeniden başlat

Masaüstü seçimi yoktur: kurulan tek masaüstü **NEOX**'tur.

---

## 5. Disk Bölümleme

### Otomatik (Önerilen - Yeni Başlayan)

Hiroki Installer → **wipe modu** →

- **ext4:** Basit, stabil
- **btrfs:** Önerilen (snapshot desteği). Otomatik subvolume:
  ```
  @         → /
  @home     → /home
  @snapshots → /.snapshots
  ```
  + `compress=zstd:1,ssd,noatime`

### Manuel (partition modu)

- **UEFI:** En az 300 MB FAT32 EFI bölümü
- **BIOS:** GRUB için `bios_grub` bölümü veya ayrı `/boot`
- `/` en az 15 GB, `ext4` veya `btrfs`
- Mevcut bölümlenmiş diskinize kurmak için `partition` modunu seçin (bölümler biçimlendirilmez)

### Dual Boot (Windows ile)

1. Windows'ta disk küçült (Disk Management → Shrink)
2. Boşta kalan bölüme Hiroki Installer'ın `partition` modu ile kurun
3. GRUB `os-prober` Windows'u otomatik bulur (`GRUB_DISABLE_OS_PROBER=false`)
4. BIOS boot sırası: Hiroki/Arch ilk

> UEFI + Windows BitLocker varsa BitLocker'ı duraklatın.

---

## 6. BIOS vs UEFI Farkları

| Özellik | BIOS (Legacy) | UEFI |
|---|---|---|
| Partition tablosu | MBR | GPT (önerilen) |
| Bootloader | GRUB MBR | GRUB ESP |
| Secure Boot | Yok | Kapat önerilir |
| Komut | `grub-install --target=i386-pc /dev/sda` | `grub-install --target=x86_64-efi --efi-directory=/boot` |

Her ikisi de Hiroki profilinde tanımlı (`profiledef.sh` → `bootmodes`).

---

## 7. Kurulum Sonrası İlk Açılış

1. GRUB → Hiroki temalı menü
2. Plymouth neox animasyonu (varsa)
3. Görüntü yöneticisi: **hiroki-dm** (Hiroki'nin kendi Wayland görüntü yöneticisi) tty1'de otomatik başlar
4. Giriş → **NEOX** Hiroki temasıyla açılır
5. **Hiroki Hoş Geldiniz** ilk açılışta → Güncelle, tema, yedek rehberi
6. `sudo pacman -Syu` ve `yay` ile sistemi güncel tut

Servisler otomatik etkin: `NetworkManager`, `bluetooth`, `cups`, `ufw`, `fstrim.timer`, `pipewire` + `wireplumber`, `hiroki-dm`

---

## 8. Kurulum Sonrası Yapılacaklar

```bash
# Güncelle
sudo pacman -Syu
# veya grafik: hiroki-update

# AUR helper (yay)
sudo pacman -S --needed git base-devel
git clone https://aur.archlinux.org/yay.git && cd yay && makepkg -si

# Sürücüler (NVIDIA vb.)
hiroki-driver-manager

# Yedek
sudo timeshift --create --comments "ilk kurulum"

# Tema
hiroki-theme-manager
```

---

## 9. Sorun Giderme

- **Wi-Fi yok:** `nmtui` veya `iwctl` ile bağlan; `lspci -k` ile sürücü kontrol et; `hiroki-driver-manager`
- **Siyah ekran (NVIDIA):** GRUB'da `e` → `nomodeset` ekle → açılış sonrası `sudo pacman -S nvidia` ve `mkinitcpio -P`
- **NEOX açılmıyor / hiroki-dm hatası:** `journalctl -u hiroki-dm -b` ile günlüğe bakın; `systemctl status hiroki-dm`
- **GRUB kayboldu (dual-boot):** Live ile aç → `sudo mount /dev/sdXn /mnt` + `sudo arch-chroot /mnt grub-install ... && grub-mkconfig -o /boot/grub/grub.cfg`
- **Btrfs snapshot geri al:** `sudo snapper list` veya `timeshift --restore`
- **Şifre unutuldu:** GRUB → `e` → `init=/bin/bash` → `passwd <kullanıcı>`

---

## 10. Kaldırma

Canlı USB ile aç → GParted → Hiroki partition'larını sil → Windows `bootrec /fixmbr` (BIOS) veya EFI'den Hiroki girdisini sil.

---

Keyifli Hiroki! 🌸 https://hiroki-os.org/support
