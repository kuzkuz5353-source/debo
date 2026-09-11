# 🌸 Hiroki OS 1.0 Neox

**Arch Linux tabanlı, Calamares yükleyicili, neox gibi zarif dağıtım.**

> Felsefe: *Donanımını tanı, ona en uygun masaüstü ortamını öner ama asla zorla. Kullanıcı her zaman son kararı verir.*

[![Versiyon](https://img.shields.io/badge/version-1.0%20Neox-E91E8C?style=flat-square)](https://hiroki-os.org)
[![Taban](https://img.shields.io/badge/taban-Arch%20Linux-1793D1?style=flat-square)](https://archlinux.org)
[![Yükleyici](https://img.shields.io/badge/yükleyici-Calamares-2D1B69?style=flat-square)](https://calamares.io)
[![Lisans](https://img.shields.io/badge/lisans-GPLv3-00D4AA?style=flat-square)](LICENSE)

---

## ✨ Özellikler

- **Arch Tabanlı & Rolling Release** — En güncel paketler, AUR hazır (yay/paru)
- **Akıllı Masaüstü Seçici (hiroki-de-selector)** — RAM, CPU, GPU ve sanal makineyi algılar, 10 ortamdan en uygununu önerir ama seçim tamamen serbest
- **11 Masaüstü / Pencere Yöneticisi:**
  - `XFCE` (live varsayılan, dengeli)
  - `KDE Plasma` (tam özellikli, 4GB+ önerilir)
  - `GNOME` (modern, Wayland)
  - `Cinnamon`, `MATE`, `Budgie`, `LXQt`
  - `i3wm`, `Openbox`, `Hyprland` (Wayland tiling)
  - `NEOX` (Hyprland tabanlı, mobil ilhamlı Wayland masaüstü — bkz. `neox-desktop/`)
- **Hiroki Tasarım Dili:**
  - Renkler: `#2D1B69` (koyu mor), `#E91E8C` (pembe), `#00D4AA` (turkuaz), `#0D0D1A` / `#1A1A2E` (koyu arkaplan)
  - **Hiroki-Dark** GTK2/3 teması (Arc Dark tabanlı)
  - **Hiroki-Icons** (Papirus Dark tabanlı, mor klasörler)
  - 5 özel duvar kağıdı: neox-gradients, geometrik dalgalar, minimalist dağ, soyut neon, uzay teması
  - GRUB, LightDM/SDDM/GDM, Plymouth temaları
- **Calamares Entegrasyonu:** Welcome → Locale → Keyboard → Partition (Btrfs subvolume `@`, `@home`, `@snapshots`) → **hiroki-de-select** → Netinstall → Users → Summary → Install
- **Hoş Geldiniz Merkezi (hiroki-welcome):** Live ve ilk açılışta donanım özetini, öneriyi ve hızlı eylemleri gösterir (GTK3/Python)
- **Araçlar:** `hiroki-theme-manager`, `hiroki-update` (pacman + AUR), `hiroki-btrfs-assistant` (Btrfs/Timeshift), `hiroki-driver-manager` (NVIDIA odaklı)
- **Türkçe Varsayılan, Çok Dilli:** `tr_TR.UTF-8`, `en_US.UTF-8`, `ja_JP.UTF-8` (+ de, fr vb.)
- **Btrfs + Timeshift, PipeWire, NetworkManager, UFW, CUPS, Bluetooth**
- **🧊 Hiroki OS Btrfs Asistanı (`hiroki-btrfs-assistant`)** — Her paket kurulumu/güncellemesi/kaldırma işleminden önce pacman hook'u üzerinden otomatik Btrfs anlık görüntüsü (snapshot) alır; `grub-btrfsd` ile bu snapshotlar GRUB önyükleme menüsüne ("Hiroki OS Neox Snapshots" alt menüsü) otomatik eklenir, böylece bir sorun anında doğrudan GRUB'dan eski bir snapshot ile açılış yapıp sisteminizi tek tıkla geri döndürebilirsiniz.
- **🌐 Gelişmiş Ağ & DNS Yönetimi (`hiroki-network-manager`)** — Cloudflare, Google, Quad9, OpenDNS, AdGuard, Yandex gibi hazır sağlayıcılar arasında tek tıkla, sistem genelinde DNS değiştirme; ayrıca ana sistem ağınızdan tamamen bağımsız/izole çalışan ayrı bir "İzole İnternet Sürücüsü" (network namespace tabanlı) ile seçtiğiniz uygulamaları izole ağ üzerinden çalıştırabilme.
- **🐧 Hiroki OS Kernel Manager (`hiroki-kernel-manager`)** — Oyun performansı için özel olarak optimize edilmiş çekirdekleri (Linux-Zen, Linux-CachyOS BORE, Linux-Xanmod, Linux-LTS, Linux-Hardened) listeler, tek tıkla indirir, kurar ve GRUB menüsüne otomatik entegre eder.
- **🎮 Hiroki OS Hello Update (`hiroki-hello-update`)** — Oyunların stabil çalışması için gereken GPU sürücülerini, 32-bit uyumluluk kütüphanelerini, Wine/Proton bağımlılıklarını ve performans yardımcılarını (GameMode, MangoHUD, Vulkan araçları vb.) otomatik tespit eder; eksikleri tek tıkla veya tamamen arka planda (günlük zamanlayıcı ile) kurar.

---

## 🖥️ Ekran Görüntüleri

> ISO derlendiğinde `/usr/share/hiroki/wallpapers/` altındaki duvar kağıtları ve Calamares slaytları (5 slayt) burada görünecek.

| Duvar Kağıdı | Açıklama |
|---|---|
| `neox-gradient.jpg` | Varsayılan: koyu lacivert üzerine mor→pembe gradyan neox dalı |
| `geometric-waves.jpg` | Geometrik dalgalar, turkuaz vurgu |
| `minimal-mountain.jpg` | Minimalist dağ, sisli |
| `abstract-neon.jpg` | Soyut neon ışıklar |
| `space-theme.jpg` | Uzay, yıldızlar ve galaksi |

---

## 🚀 Hızlı Başlangıç

### ISO İndir
```bash
# Yakında: https://hiroki-os.org/download
# Şimdilik kendiniz derleyin (bkz. BUILDING.md)
```

### USB'ye Yaz
```bash
sudo dd if=hiroki-os-1.0-x86_64.iso of=/dev/sdX bs=4M status=progress oflag=sync
# veya Ventoy, Etcher, Popsicle
```

### Live Dene
- Boot menüsü: **"Hiroki OS'u Dene"** → XFCE live, otomatik giriş (`hiroki`/parola yok)
- Masaüstünde **Hiroki Hoş Geldiniz** otomatik açılır → **Masaüstü Ortamı Seç** ile donanımınıza göre öneriyi görün
- **Calamares** kısayolu ile kurun

---

## 🧠 Akıllı Masaüstü Öneri Matrisi

| RAM | Tier | Birinci Öneri | Alternatif | Mesaj |
|---|---|---|---|---|
| ≤512 MB | minimal | i3wm / Openbox | LXQt | Donanımınız çok sınırlı, pencere yöneticisi önerilir |
| 512 MB – 2 GB | light | LXQt | XFCE | Hafif masaüstü için uygun |
| 2 – 4 GB | medium | XFCE | LXQt, MATE | Orta seviye için uygun |
| 4 – 8 GB | full | KDE Plasma | XFCE, GNOME, Cinnamon, Budgie | Tam özellikli için uygun |
| ≥8 GB | high | KDE + GNOME | Tümü | Tüm ortamları rahatça çalıştırabilir |

> `hiroki-hw-detect` → `/tmp/hiroki-hw-info.json` → hem `hiroki-de-selector` GUI hem Calamares modülü aynı dosyayı okur. Uyarı: 512 MB + GNOME seçilirse `“Ağır olabilir, devam edilsin mi?”` onayı istenir ama kurulum engellenmez.

---

## 🛠️ Derleme

```bash
git clone https://github.com/hiroki-os/hiroki-os.git
cd hiroki-os/hiroki-os
sudo ./build.sh
# Çıktı: out/hiroki-os-1.0-x86_64.iso + .sha256 + .md5
```

Detaylı: [BUILDING.md](BUILDING.md)  
Kurulum rehberi: [INSTALL.md](INSTALL.md)  
Tema özelleştirme: [CUSTOMIZATION.md](CUSTOMIZATION.md)

---

## 📁 Proje Yapısı (Özet)

```
hiroki-os/
├── airootfs/              # ISO kök dosya sistemi
│   ├── etc/{hostname,locale.conf,os-release,calamares,hiroki/...}
│   ├── usr/{bin/hiroki-*,share/hiroki,share/themes/Hiroki-Dark}
│   └── etc/skel/          # Yeni kullanıcı iskeleti (.bashrc, autostart)
├── efiboot/ grub/ syslinux/ # Bootloader'lar
├── packages.x86_64        # Paket listesi (kategorili)
├── pacman.conf            # multilib aktif
├── profiledef.sh          # Archiso profili (HIROKI_OS)
└── build.sh               # Derleme scripti (16 adım)
```

Tam harita: `CUSTOMIZATION.md` ve `docs/FILEMAP.md`

---

## 🤝 Katkıda Bulunma

Katkılarınız neox yaprakları gibi değerli! Bkz. [CONTRIBUTING.md](CONTRIBUTING.md)

1. Fork → branch (`feature/tema-v2`)
2. Commit (`git commit -m "feat: Hyprland blur eklendi"`)
3. Push → Pull Request

Issue: https://github.com/hiroki-os/hiroki-os/issues

---

## 📄 Lisans

GPL-3.0 — Bkz. [LICENSE](LICENSE)

---

## 🌸 Hiroki OS Project

- Web: https://hiroki-os.org
- Wiki: https://wiki.hiroki-os.org
- Destek: https://hiroki-os.org/support
- Sürüm Notları: https://hiroki-os.org/releases/1.0

> Hiroki OS, Arch Linux topluluğuna ve açık kaynak dünyasına teşekkür eder. Neox gibi zarif, Arch gibi güçlü kalın.
