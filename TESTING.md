# ✅ Hiroki OS Kalite Güvencesi ve Test Kontrol Listesi

Neox 1.0 için test senaryoları. Her biri ISO derleme sonrası fiziksel/VM ortamında
doğrulanmalı. Hiroki OS artık tek masaüstü sunar: **NEOX** (Hyprland tabanlı, Wayland);
kurulum Calamares yerine kendi **Hiroki Installer**'ımızla (PyQt6) yapılır.

---

## ISO Derleme

- [ ] **1. ISO başarıyla derleniyor mu**
  - `sudo ./build.sh` hatasız bitiyor mu? `out/*.iso` + `.sha256` + `.md5` oluşuyor mu?
  - `sha256sum -c out/*.sha256` doğruluyor mu?

## Boot

- [ ] **2. BIOS modunda boot ediyor mu**
  - QEMU BIOS: `qemu-system-x86_64 -enable-kvm -m 4096 -cdrom out/*.iso -boot d` (OVMF olmadan)
  - Syslinux menüsü görünüyor mu?
- [ ] **3. UEFI modunda boot ediyor mu**
  - QEMU UEFI: `qemu-system-x86_64 -bios /usr/share/edk2-ovmf/x64/OVMF.fd -enable-kvm -m 4096 -cdrom out/*.iso -boot d`
  - GRUB Hiroki temalı menü görünüyor mu? Secure Boot kapalı mı?

## Live Oturum

- [ ] **4. Live oturum düzgün açılıyor mu**
  - `hiroki-dm.service` tty1'de otomatik başlıyor mu (`systemctl status hiroki-dm`)?
  - NEOX (Hyprland) masaüstü açılıyor mu? `live` kullanıcısı ile otomatik giriş çalışıyor mu?
  - NetworkManager aktif mi?
- [ ] **5. Hoş geldiniz uygulaması çalışıyor mu**
  - `hiroki-welcome` otomatik açılıyor mu? Live modda "Hiroki Installer'ı Başlat" ve "Hakkında" kartları görünüyor mu?
- [ ] **6. Donanım algılama doğru çalışıyor mu**
  - `hiroki-hw-detect` → `cat /tmp/hiroki-hw-info.json` → RAM, CPU, GPU, disk, virt doğru mu?
  - 4 GB altı RAM'de "NEOX için önerilen RAM'in altında" mesajı görünüyor mu?

## NEOX Masaüstü

- [ ] **7. NEOX panel ve kabuk bileşenleri çalışıyor mu**
  - `neox-panel`, `neox-shell`, `neox-desktop-grid` başlıyor mu?
  - `Super` tuşu görev değiştiriciyi (`neox-task-switcher`) açıyor mu?
  - `Super+Space` uygulama aramasını (`neox-app-search`) açıyor mu?
- [ ] **8. Hyprland temel işlevleri çalışıyor mu**
  - Pencere açma/kapama, workspace geçişi (`Super+1..9`), ekran görüntüsü (`Print`) çalışıyor mu?
  - Blur, gölge, rounded corners görünüyor mu?

## Hiroki Installer

- [ ] **9. Hiroki Installer başlıyor mu**
  - Masaüstü kısayolundan veya `hiroki-installer-launch` ile PyQt6 penceresi açılıyor mu?
- [ ] **10. Hiroki Installer tüm adımları geçilebiliyor mu**
  - Mod seçimi (wipe/partition) → disk/bölüm → kullanıcı/parola → dil/klavye/saat dilimi → önizleme → onay → kurulum → bitti sırası çalışıyor mu?
- [ ] **11. Kurulum başarıyla tamamlanıyor mu**
  - 15 GB disk alt sınırı kontrolü çalışıyor mu? Hata olmadan %100'e ulaşıyor mu? Log `/var/log/hiroki-installer/` temiz mi?

## Kurulum Sonrası

- [ ] **12. Kurulum sonrası sistem boot ediyor mu**
  - Yeniden başlat → GRUB Hiroki temalı mı? Plymouth neox animasyonu görünüyor mu?
- [ ] **13. NEOX ve hiroki-dm doğru kurulmuş mu**
  - `systemctl is-enabled hiroki-dm.service` → `enabled` mi?
  - `cat /etc/hiroki/selected-de` → `neox` mü?
  - `ls /usr/share/neox-desktop` ve `~/.config/hypr/hyprland.conf` mevcut mu?
- [ ] **14. Hiroki teması düzgün uygulanmış mı**
  - GTK `Hiroki-Dark`, ikon `Hiroki-Icons`, duvar kağıdı `neox-gradient`, terminalde Hiroki ASCII (fastfetch/hiroki-neofetch), GRUB tema `/boot/grub/grub.cfg` içinde `GRUB_THEME` doğru mu?
- [ ] **15. Ses çalışıyor mu**
  - `pavucontrol` → PipeWire + WirePlumber aktif mi? Hoparlör testi: `speaker-test -c 2 -t wav`
- [ ] **16. Ağ bağlantısı çalışıyor mu**
  - `NetworkManager` etkin mi? `ping archlinux.org` ve Wi-Fi listesi görünüyor mu?
- [ ] **17. Bluetooth çalışıyor mu (donanım varsa)**
  - `bluetooth.service` aktif mi? `bluetoothctl scan on` cihaz buluyor mu?

## Kenar Senaryolar

- [ ] **18. Düşük RAM senaryosu test edildi mi**
  - QEMU `-m 2048` → `hiroki-hw-detect` uyarı mesajı doğru mu; kurulum yine de tamamlanabiliyor mu?
- [ ] **19. VirtualBox'ta çalışıyor mu**
  - VirtualBox 7+ → Arch 64-bit, 4096 MB, EFI açık, 20 GB VDI → Hiroki live ve kurulum sorunsuz mu? Guest Additions (`virtualbox-guest-utils`) otomatik mi?
- [ ] **20. VMware'de çalışıyor mu**
  - VMware Workstation/Player → EFI, 4 GB RAM → boot ve kurulum?
- [ ] **21. Gerçek donanımda çalışıyor mu**
  - Fiziksel laptop/desktop (Intel/AMD/NVIDIA) → Wi-Fi, ses, GPU (Mesa/NVIDIA), yazıcı (CUPS) çalışıyor mu? `hiroki-driver-manager` eksik sürücüyü buluyor mu?

## Btrfs ve Ek Özellikler

- [ ] **22. hiroki-installer kurulum kökü varsayılan olarak Btrfs mi**
  - "Diski tamamen sil ve kur" (wipe) modunda kurulum sonrası `findmnt -no FSTYPE /` → `btrfs` dönüyor mu?
  - `btrfs subvolume list /` çıktısında `@`, `@home`, `@snapshots` subvolume'ları görünüyor mu; `/home` ve `/.snapshots` bu subvolume'lara doğru bağlı mı?
  - `/etc/fstab` içinde kök satırında `subvol=@` seçeneği var mı?
  - "Biçimlendirilmiş bölüme kur" (partition) modunda kullanıcının önceden hazırladığı bölümün dosya sistemi değişmeden korunuyor mu?
- [ ] **23. Btrfs Asistanı otomatik snapshot alıyor mu**
  - Btrfs kurulumda bir paket kurup/kaldırıp `timeshift --list` çıktısında yeni bir snapshot oluştuğu görülüyor mu? (`/etc/pacman.d/hooks/95-hiroki-btrfs-assistant.hook` PreTransaction'da çalışıyor mu?)
- [ ] **24. GRUB'dan snapshot ile açılış yapılabiliyor mu**
  - `grub-btrfsd` servisi aktif mi? Yeniden başlatınca GRUB'da "Hiroki OS Neox Snapshots" alt menüsü görünüyor mu, seçilen snapshot ile açılış yapılabiliyor mu?
- [ ] **25. Tek tıkla DNS değiştirme çalışıyor mu**
  - `hiroki-network-manager` içinden bir sağlayıcı seçilip uygulandığında `resolvectl status` / `nmcli` çıktısında DNS değişti mi?
- [ ] **26. İzole internet sürücüsü çalışıyor mu**
  - "İzole Ağı Etkinleştir" sonrası `ip netns list` içinde `hiroki-isolated-net` görünüyor mu? `ip netns exec hiroki-isolated-net ping 1.1.1.1` başarılı mı?
- [ ] **27. Kernel Manager ile çekirdek kurulumu çalışıyor mu**
  - `hiroki-kernel-manager` üzerinden `linux-zen` seçilip kurulduğunda paket kuruluyor ve `grub-mkconfig` sonrası GRUB menüsünde yeni giriş beliriyor mu?
- [ ] **28. Hello Update eksik bileşenleri doğru tespit ediyor mu**
  - `hiroki-hello-update --scan` çıktısı, kurulu olmayan `lib32-*`/`gamemode`/`mangohud` gibi paketleri listeliyor mu? GUI'den "Eksikleri Tek Tıkla Kur" sonrası liste boşalıyor mu?
- [ ] **29. Marka adı her yerde "Hiroki OS Neox" mı**
  - `/etc/os-release`, GRUB teması, Plymouth, `hiroki-welcome`, Hiroki Installer ekranlarının hiçbirinde eski/yanlış isim kalmamış mı?

---

### Raporlama

Her test için:

- Ortam (QEMU/VBox/VMware/gerçek, RAM, CPU, GPU)
- ISO hash (`sha256sum`)
- Sonuç (✅ / ❌) + log (`/tmp/hiroki-hw-info.json`, `/var/log/hiroki-installer/`, `journalctl -b`)
- Ekran görüntüsü

Başarı kriteri: tüm testler yeşil. Eksik varsa issue aç: https://github.com/hiroki-os/hiroki-os/issues
