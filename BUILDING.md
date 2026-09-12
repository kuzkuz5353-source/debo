# 🔨 Hiroki OS Derleme Kılavuzu

Bu belge Hiroki OS 1.0 Neox ISO'sunu sıfırdan nasıl derleyeceğinizi adım adım anlatır.

> **Not:** Bu proje Archiso tabanlıdır. Derleme **temiz bir Arch Linux** ortamında (fiziksel, VM veya container/chroot) yapılmalıdır. Debian/Ubuntu üzerinde doğrudan derlenmez.

---

## 1. Gereksinimler

### Ortam
- Arch Linux (en güncel, `pacman -Syu` yapılmış)
- En az 20 GB boş disk, 4 GB RAM
- Root erişimi (`sudo`)

### Paketler
```bash
sudo pacman -Syu --needed \
  archiso \
  squashfs-tools \
  grub \
  edk2-ovmf \
  dosfstools \
  mtools \
  erofs-utils \
  libisoburn \
  arch-install-scripts \
  git \
  make \
  python \
  python-gobject \
  python-pyqt6  # hiroki-installer bağımlılıkları için gerekebilir
```

Kontrol:
```bash
which mkarchiso
mkarchiso --version
```

---

## 2. Kaynağı Al

```bash
git clone https://github.com/hiroki-os/hiroki-os.git
cd hiroki-os/hiroki-os
ls -l  # profiledef.sh, packages.x86_64, build.sh, airootfs/ görünmeli
```

> Bu prompt'u Archiso temeli olmadan çalıştırıyorsanız, `hiroki-os/` dizini bu repo içindeki tüm özelleştirmeleri zaten içerir; Archiso'nun `releng` profilini ayrıca indirmenize gerek yoktur — `build.sh` kendi profilini kullanır.

---

## 3. Paket Listesini Gözden Geçir

```bash
cat packages.x86_64
# Kategoriler: Temel Sistem, Dosya Sistemi, Wayland/XWayland, GPU, Yazı Tipleri,
# Hiroki Installer, Ortak Masaüstü Uygulamaları, Ses/Multimedya, NEOX Masaüstü
```

İsteğe bağlı: `pacman.conf` içinde `multilib` zaten açıktır; Hiroki deposu yorum satırındadır.

---

## 4. Derleme

### Tek Komut (Önerilen)
```bash
sudo ./build.sh
```

`build.sh` sırasıyla şu adımları yapar:

1. Bağımlılık kontrolü (`archiso`, `squashfs-tools` vb.)
2. Çalışma dizini oluştur (`/tmp/hiroki-build-work`)
3. Archiso profil dosyalarını kopyala
4. Hiroki özelleştirmelerini uygula
5. Paket listesini oku ve doğrula
6. `pacman.conf` yapılandır (multilib)
7. `airootfs` dosya sistemini oluştur
8. Hiroki tema dosyalarını yerleştir
9. Hoş geldiniz uygulamasını yerleştir
10. Özel araçları yerleştir (hiroki-installer dahil)
11. systemd servislerini yapılandır (live, hiroki-dm)
12. Live kullanıcısını yapılandır (otomatik giriş, NEOX/hiroki-dm)
13. squashfs sıkıştırması yap
14. ISO oluştur
15. SHA256 ve MD5 checksum oluştur
16. Çıktı: `out/hiroki-os-1.0-x86_64.iso`

### Manuel (Archiso doğrudan)
```bash
sudo mkarchiso -v -w /tmp/hiroki-work -o ./out ./
# Profil dizini olarak hiroki-os/ dizinini gösterir
```

---

## 5. Çıktılar

Başarılı derlemede:
```
out/
├── hiroki-os-1.0-x86_64.iso        # Kurulabilir ISO
├── hiroki-os-1.0-x86_64.iso.sha256
├── hiroki-os-1.0-x86_64.iso.md5
└── hiroki-os-1.0-x86_64.iso.info
```

Doğrulama:
```bash
sha256sum -c out/hiroki-os-*.iso.sha256
ls -lh out/
```

---

## 6. Test

### QEMU (hızlı)
```bash
qemu-system-x86_64 -enable-kvm -m 4096 -cdrom out/hiroki-os-*.iso -boot d
# Düşük RAM testi: -m 2048
# UEFI testi: -bios /usr/share/edk2-ovmf/x64/OVMF.fd
```

### VirtualBox / VMware

- Yeni VM → Linux → Arch 64-bit → 4096 MB RAM, 20 GB disk, EFI etkin
- ISO'yu bağla → Başlat → **Hiroki OS'u Dene** → Hiroki Installer ile kur

### Gerçek Donanım

```bash
lsblk  # USB aygıtı bul (örn. /dev/sdb)
sudo dd if=out/hiroki-os-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
# veya Ventoy, Etcher, SUSE Studio Imagewriter
```

---

## 7. Sorun Giderme

| Sorun | Çözüm |
|---|---|
| `mkarchiso not found` | `sudo pacman -S archiso` |
| `failed to install packages` | `sudo pacman -Syu` yap, mirror yenile: `reflector --latest 5 --sort rate --save /etc/pacman.d/mirrorlist` |
| `no space left` | `/tmp` en az 15 GB boş olmalı; `WORK_DIR` başka diske al: `sudo mkdir -p /mnt/big/work && sudo ./build.sh` içinde `WORK_DIR` değiştir |
| `permission denied` | `sudo` ile çalıştır, `chmod +x build.sh` |
| Hiroki Installer başlamıyor | `sudo python3 /usr/bin/hiroki-installer --check` ile bağımsız kontrol çalıştır; PyQt6 kurulu mu doğrula |
| ISO boot etmiyor (UEFI) | `profiledef.sh` içinde `bootmodes` UEFI içermeli; `edk2-ovmf` kurulu mu kontrol et |
| Paket bulunamadı | Paket ismi güncel mi kontrol et: `pacman -Ss <isim>`; AUR paketleri `packages.x86_64` içine eklenmemeli (yay/paru ile kurulur) |

### Temiz Derleme

```bash
sudo rm -rf /tmp/hiroki-build-work out/
sudo ./build.sh
```

---

## 8. Geliştirme İpuçları

- **Hızlı iterasyon:** Tüm sistemi değil sadece `airootfs` içindeki bir script'i test etmek için ISO'yu açmadan `arch-chroot` kullan:
  ```bash
  sudo mkdir -p /tmp/airootfs-test
  sudo mount -o loop out/hiroki-os-*.iso /mnt
  sudo unsquashfs -f -d /tmp/airootfs-test /mnt/arch/x86_64/airootfs.sfs
  sudo arch-chroot /tmp/airootfs-test /usr/bin/hiroki-hw-detect
  ```
- **hiroki-installer paket listesi:** `DES["neox"]["packages"]` içindeki paketler `pacman -Si` ile doğrulanabilir.
- **Tema:** GTK değişiklikleri için `GTK_DEBUG=interactive gtk3-widget-factory` ile canlı test.

---

## 9. Sürüm Çıkarma

- `profiledef.sh` → `iso_version`
- `airootfs/etc/os-release` → `VERSION`
- `airootfs/usr/bin/hiroki-installer` → `VERSION`
- `README.md` ve `BUILDING.md` güncelle
- `git tag v1.0 && git push origin v1.0`

---

Başarılar! 🌸 Sorular için https://github.com/hiroki-os/hiroki-os/issues
