# ✅ Hiroki OS Kalite Güvencesi ve Test Kontrol Listesi

Neox 1.0 için 21 test senaryosu. Her biri ISO derleme sonrası fiziksel/VM ortamında doğrulanmalı.

---

## ISO Derleme

- [ ] **1. ISO başarıyla derleniyor mu**
  - `sudo ./build.sh` hatasız bitiyor mu? `out/*.iso` + `.sha256` + `.md5` oluşuyor mu?
  - `sha256sum -c out/*.sha256` doğruluyor mu?

## Boot

- [ ] **2. BIOS modunda boot ediyor mu**
  - QEMU BIOS: `qemu-system-x86_64 -enable-kvm -m 2048 -cdrom out/*.iso -boot d` (OVMF olmadan)
  - Syslinux menüsü görünüyor mu?
- [ ] **3. UEFI modunda boot ediyor mu**
  - QEMU UEFI: `qemu-system-x86_64 -bios /usr/share/edk2-ovmf/x64/OVMF.fd -enable-kvm -m 2048 -cdrom out/*.iso -boot d`
  - GRUB Hiroki temalı menü görünüyor mu? Secure Boot kapalı mı?

## Live Oturum

- [ ] **4. Live oturum düzgün açılıyor mu**
  - Varsayılan XFCE masaüstü açılıyor mu? Otomatik giriş `hiroki` çalışıyor mu? NetworkManager aktif mi?
- [ ] **5. Hoş geldiniz uygulaması çalışıyor mu**
  - `hiroki-welcome` otomatik açılıyor mu? Live modda 3 kart (DE Seç, Kuruluma Başla, Hakkında) görünüyor mu?
- [ ] **6. Donanım algılama doğru çalışıyor mu**
  - `hiroki-hw-detect` → `cat /tmp/hiroki-hw-info.json` → RAM, CPU, GPU, disk, virt doğru mu?
  - `512 MB`, `2 GB`, `8 GB` için farklı tier üretiyor mu?
- [ ] **7. Masaüstü ortamı önerisi doğru mu**
  - 512 MB → i3wm/Openbox uyarısı, 1 GB → LXQt, 3 GB → XFCE, 6 GB → KDE, 16 GB → KDE+GNOME
  - `hiroki-de-selector` GUI solda donanım, sağda öneri kartı + 10 DE grid gösteriyor mu?

## Calamares

- [ ] **8. Calamares başlıyor mu**
  - Masaüstü kısayolundan `sudo -E calamares` çalışıyor mu? Branding (900x600, Hiroki mor/pembe, Hiroki logosu) doğru mu?
- [ ] **9. Calamares tüm adımları geçilebiliyor mu**
  - Welcome → Locale → Keyboard → Partition (ext4/btrfs + subvolumes + swap) → **hiroki-de-select** → Netinstall → Users → Summary → Install → Finished sırası korunuyor mu?
- [ ] **10. Kurulum başarıyla tamamlanıyor mu**
  - 15 GB disk, 512 MB RAM alt sınırı kontrolü çalışıyor mu? Hata olmadan %100’e ulaşıyor mu? Log `/var/log/calamares/` temiz mi?

## Kurulum Sonrası

- [ ] **11. Kurulum sonrası sistem boot ediyor mu**
  - Yeniden başlat → GRUB Hiroki temalı mı? Plymouth neox animasyonu görünüyor mu?
- [ ] **12. Seçilen masaüstü ortamı doğru kurulmuş mu**
  - `pacman -Q | grep xfce` / `plasma-meta` / `gnome` vb. Seçilen DE'nin paketleri ve `cat /etc/hiroki/selected-de` eşleşiyor mu?
- [ ] **13. Hiroki teması düzgün uygulanmış mı**
  - GTK `Hiroki-Dark`, ikon `Hiroki-Icons`, duvar kağıdı `neox-gradient`, terminalde Hiroki ASCII (fastfetch/neofetch), GRUB tema `/boot/grub/grub.cfg` içinde `GRUB_THEME` doğru mu?
- [ ] **14. Ses çalışıyor mu**
  - `pavucontrol` → PipeWire + WirePlumber aktif mi? Hoparlör testi: `speaker-test -c 2 -t wav`
- [ ] **15. Ağ bağlantısı çalışıyor mu**
  - `NetworkManager` etkin mi? `ping archlinux.org` ve Wi-Fi listesi görünüyor mu?
- [ ] **16. Bluetooth çalışıyor mu (donanım varsa)**
  - `bluetooth.service` aktif mi? `bluetoothctl scan on` cihaz buluyor mu?

## Her DE

- [ ] **17. Her masaüstü ortamı seçeneği ayrı ayrı test edildi mi**
  - 10 DE için ayrı VM kurulumu: XFCE, KDE, GNOME, Cinnamon, MATE, Budgie, LXQt, i3wm, Openbox, Hyprland → giriş, tema, uygulama (Thunar/Dolphin/Nautilus) açılıyor mu?
  - i3/Hyprland kısayollar (Mod+Enter, Mod+d) çalışıyor mu? Waybar/polybar görünüyor mu?

## Kenar Senaryolar

- [ ] **18. Düşük RAM senaryosu test edildi mi**
  - QEMU `-m 512` → LXQt/i3 önerisi, GNOME seç → uyarı dialogu → onay → kurulum devam ediyor mu?
- [ ] **19. VirtualBox'ta çalışıyor mu**
  - VirtualBox 7+ → Arch 64-bit, 2048 MB, EFI açık, 20 GB VDI → Hiroki live ve kurulum sorunsuz mu? Guest Additions (`virtualbox-guest-utils`) otomatik mi?

## Sanallaştırma ve Donanım

- [ ] **20. VMware'de çalışıyor mu**
  - VMware Workstation/Player → EFI, 2 GB RAM → boot ve kurulum?
- [ ] **21. Gerçek donanımda çalışıyor mu**
  - Fiziksel laptop/desktop (Intel/AMD/NVIDIA) → Wi-Fi, ses, GPU (Mesa/NVIDIA), yazıcı (CUPS) çalışıyor mu? `hiroki-driver-manager` eksik sürücüyü buluyor mu?

## Yeni Özellikler (Neox)

- [ ] **22. Btrfs Asistanı otomatik snapshot alıyor mu**
  - Btrfs kurulumda bir paket kurup/kaldırıp `timeshift --list` çıktısında yeni bir snapshot oluştuğu görülüyor mu? (`/etc/pacman.d/hooks/95-hiroki-btrfs-assistant.hook` PreTransaction'da çalışıyor mu?)
- [ ] **23. GRUB'dan snapshot ile açılış yapılabiliyor mu**
  - `grub-btrfsd` servisi aktif mi? Yeniden başlatınca GRUB'da "Hiroki OS Neox Snapshots" alt menüsü görünüyor mu, seçilen snapshot ile açılış yapılabiliyor mu?
- [ ] **24. Tek tıkla DNS değiştirme çalışıyor mu**
  - `hiroki-network-manager` içinden bir sağlayıcı seçilip uygulandığında `resolvectl status` / `nmcli` çıktısında DNS değişti mi?
- [ ] **25. İzole internet sürücüsü çalışıyor mu**
  - "İzole Ağı Etkinleştir" sonrası `ip netns list` içinde `hiroki-isolated-net` görünüyor mu? `ip netns exec hiroki-isolated-net ping 1.1.1.1` başarılı mı?
- [ ] **26. Kernel Manager ile çekirdek kurulumu çalışıyor mu**
  - `hiroki-kernel-manager` üzerinden `linux-zen` seçilip kurulduğunda paket kuruluyor ve `grub-mkconfig` sonrası GRUB menüsünde yeni giriş beliriyor mu?
- [ ] **27. Hello Update eksik bileşenleri doğru tespit ediyor mu**
  - `hiroki-hello-update --scan` çıktısı, kurulu olmayan `lib32-*`/`gamemode`/`mangohud` gibi paketleri listeliyor mu? GUI'den "Eksikleri Tek Tıkla Kur" sonrası liste boşalıyor mu?
- [ ] **28. Marka adı her yerde "Hiroki OS Neox" mı**
  - `/etc/os-release`, GRUB teması, Plymouth, SDDM, `hiroki-welcome`, kurulum sihirbazı ekranlarının hiçbirinde "Sakura" ibaresi kalmamış mı? Kurulum sonrası hedef sistemde de aynı doğrulama yapılmış mı?

---

### Raporlama

Her test için:

- Ortam (QEMU/VBox/VMware/gerçek, RAM, CPU, GPU)
- ISO hash (`sha256sum`)
- Sonuç (✅ / ❌) + log (`/tmp/hiroki-hw-info.json`, `/var/log/calamares/`, `journalctl -b`)
- Ekran görüntüsü

Başarı kriteri: 21/21 yeşil. Eksik varsa issue aç: https://github.com/hiroki-os/hiroki-os/issues
