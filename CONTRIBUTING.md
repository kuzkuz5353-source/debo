# 🤝 Katkıda Bulunma — Hiroki OS

Neox yaprakları gibi her katkı değerlidir. Teşekkürler!

---

## 1. Nasıl Katkıda Bulunulur

### Hata Bildir (Issue)

- https://github.com/hiroki-os/hiroki-os/issues → **New Issue**
- Şablon: Başlık, açıklama, adımlar, beklenen/gerçek sonuç, `hiroki-hw-detect` çıktısı, hiroki-installer log (`/var/log/hiroki-installer/`)

### Özellik İsteği

- Aynı issue sayfasında **Feature Request** etiketiyle açın; NEOX masaüstüne veya Hiroki Installer'a yönelik öneriler için tartışalım (Hiroki OS artık tek masaüstü sunar: NEOX)

### Kod Katkısı (Pull Request)

1. Fork → `git clone https://github.com/<sen>/hiroki-os.git`
2. Branch: `git checkout -b feature/kisa-aciklama`
3. Değiştir, test et (QEMU/VirtualBox)
4. Commit: Conventional Commits (`feat:`, `fix:`, `docs:`, `style:`)
   ```
   feat(neox): panel için VRAM kontrolü eklendi
   fix(hiroki-installer): btrfs subvolume compress bayrağı düzeltildi
   ```
5. Push → GitHub'da **Pull Request** aç, şablonu doldur

---

## 2. Kod Stili

- **Bash:** `shellcheck` temiz, `set -euo pipefail`, shebang `#!/usr/bin/env bash`, fonksiyonlar `snake_case`
- **Python (GTK/PyQt6):** PEP8, `python -m py_compile`, Türkçe yorumlarda UTF-8, `gi.require_version` doğru
- **NEOX (Hyprland) config:** `neox-desktop/compositor/hyprland.conf` sözdizimi Hyprland resmi wiki ile uyumlu
- **Archiso:** Resmi Arch Wiki ile uyumlu; paket isimleri `pacman -Si` ile doğrulanmış
- **Tema CSS:** Renkler sadece Hiroki paleti (`#2D1B69`, `#E91E8C`, `#00D4AA`, `#0D0D1A`, `#1A1A2E`)
- **Commit mesajı:** Türkçe veya İngilizce, açıklayıcı, tek satır özet + detaylı gövde

---

## 3. Test

PR öncesi kontrol listesi (bkz. TESTING.md):

- [ ] `shellcheck build.sh airootfs/usr/bin/hiroki-*`
- [ ] `python3 -m py_compile airootfs/usr/share/hiroki-welcome/*.py airootfs/usr/bin/hiroki-installer`
- [ ] QEMU'da 2 GB, 4 GB, 8 GB RAM ile ayrı test
- [ ] Hiroki Installer tüm adımları geçiyor, kurulum sonrası NEOX ile boot ediyor

---

## 4. İletişim

- Tartışma: GitHub Discussions
- E-posta: hiroki-os@example.org (örnek, gerçek adres repo'da)
- Davranış Kuralları: Saygılı, kapsayıcı, ayrımcılık yok (Contributor Covenant)

---

## 5. Lisans

Katkılarınız GPL-3.0 altında lisanslanır. Bkz. LICENSE.

---

Arigato! 🌸
