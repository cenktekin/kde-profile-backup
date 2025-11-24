# KDE Backup/Restore (konsave + packages + flatpak)

KDE Plasma ayarlarını (konsave), distro paket listesini, Flatpak uygulamalarını ve ek kullanıcı verilerini yedekleyip geri yüklemenize yardımcı olan basit bir araç.

- Betik: `scripts/kde_backup_restore.py`
- Yedek hedefi: `kde-backups/` (çalıştırdığınız klasör içinde zaman damgalı klasör oluşturur)

## Gereksinimler
- Python 3.8+
- `konsave` (KDE ayarları için)
- Paket yöneticiniz (Fedora: `dnf`, Debian/Ubuntu: `apt`, Arch: `pacman`, openSUSE: `zypper`)
- `flatpak` (opsiyonel; Flatpak yedeklemek istiyorsanız)

Kurulum (konsave):
```bash
python -m pip install --user konsave
```

> Not: KDE ayarlarının tam uygulanması için bazen oturumu kapatıp açmak gerekir.

## Çalıştırma
Proje kökünde:
```bash
python scripts/kde_backup_restore.py
```

### Menü
- `1) Full Backup (konsave + packages + flatpak + extra-*)`:
  - Konsave profilini `.knsv` olarak dışa aktarır.
  - Distro paket listesini `packages.txt` olarak, Flatpak uygulamalarını `flatpaks.txt` olarak kaydeder.
  - `extra-config/` ve `extra-data/` klasörlerini oluşturur (aşağıya bakınız).
- `2) Restore (konsave import/apply + opsiyonel extra-*)`:
  - `.knsv` profili içe aktarılır ve uygulanır; `extra-config/` ve `extra-data/` kopyalama isteğe bağlı sorulur.
  - Paket/Flatpak kurulum komutları **gösterilir** (otomatik çalıştırılmaz).
- `3) Quick Backup (incremental extra-*)`:
  - Sadece `extra-config/` ve `extra-data/` için değişen/yeni dosyaları `kde-backups/latest/` altına senkronlar; kaynakta silinenleri `latest/`tan kaldırır.
  - İsteğe bağlı olarak hızlı konsave export yapılabilir.

## Yedek Çıktısı
- Full Backup: `kde-backups/<timestamp>/`
  - `<profil>.knsv` (konsave profili)
  - `packages.txt` (ana paket yöneticisi paket listesi)
  - `flatpaks.txt` (flatpak ref listesi)
  - `system-packages.json` (tüm sistem paketleri - pacman/dnf/apt/zypper + AUR + Flatpak - JSON formatında)
  - `aur-packages.txt` (AUR paketleri)
  - `flatpak-packages.txt` (Flatpak paketleri ayrı liste)
  - `pacman-packages.txt` (pacman paketleri ayrı liste)
  - `extra-config/` (kritik KDE konfigleri)
  - `extra-data/` (seçilmiş kullanıcı verileri)
  - `meta.json`
- Quick Backup: `kde-backups/latest/`
  - `extra-config/` ve `extra-data/` senkron kopyası + `meta.json`

## Geri Yükleme İpuçları
- KDE değişiklikleri tam yansımazsa oturumu kapatıp açın.
- Paket/Flatpak kurulum önerileri:
  - Fedora (dnf):
    ```bash
    sudo dnf install -y $(cat kde-backups/<timestamp>/packages.txt)
    ```
  - Debian/Ubuntu (apt):
    ```bash
    sudo apt install -y $(cat kde-backups/<timestamp>/packages.txt)
    ```
  - Arch (pacman):
    ```bash
    sudo pacman -S --needed - < kde-backups/<timestamp>/packages.txt
    ```
  - openSUSE (zypper):
    ```bash
    sudo xargs -a kde-backups/<timestamp>/packages.txt zypper in -y
    ```
  - Flatpak:
    ```bash
    xargs -a kde-backups/<timestamp>/flatpaks.txt -r -L1 flatpak install -y --noninteractive
    ```

## Extra Katmanları
- `extra-config/` (kritik KDE ayar dosyaları):
  - `~/.config/plasma-org.kde.plasma.desktop-appletsrc`
  - `~/.config/kdeglobals`
  - `~/.config/kwinrc`
  - `~/.config/mimeapps.list` (dosya türü ilişkilendirmeleri)
- `extra-data/` (kullanıcı verileri – örnekler):
  - `~/.local/share/applications/`
  - `~/.local/share/plasma_notes/`
  - `~/.local/share/plasma-systemmonitor/`
  - `~/.local/zed-preview.app/`
  - `~/.config/autostart/` (otomatik başlatma uygulamaları)
  - `~/.ssh/` (SSH anahtarları ve yapılandırması)
  - `~/.gnupg/` (GPG anahtarları)
  - `~/.pki/` (SSL sertifikaları)
  - `~/.mozilla/` (Firefox tarayıcı profilleri)
  - `~/.config/BraveSoftware/` (Brave tarayıcı profilleri - nightly dahil)
  - `~/.config/google-chrome/` (Chrome tarayıcı profilleri)
  - `~/.config/chromium/` (Chromium tarayıcı profilleri)
  - Ana dizindeki yapılandırma dosyaları:
    - `.gitconfig`, `.gtkrc-2.0`, `.viminfo`, `.zshrc`, `.bashrc`, `.bash_profile`, `.p10k.zsh`

## CLI Kısayolları
```bash
# Full backup
python scripts/kde_backup_restore.py --full

# Quick backup (incremental extra-*)
python scripts/kde_backup_restore.py --quick

# Verify son/Seçili yedeği
python scripts/kde_backup_restore.py --verify

# Restore (etkileşimli seçim)
python scripts/kde_backup_restore.py --restore

# Restore Preview (ön izleme)
python scripts/kde_backup_restore.py --preview latest
python scripts/kde_backup_restore.py --preview 20250829-151354

# Konsave ekstra argümanları (ileri seviye)
python scripts/kde_backup_restore.py --full --konsave-args "<konsave-argümanları>"

# Tag & Scope ile yedek/restore
# Tag ekleyerek full backup
python scripts/kde_backup_restore.py --full --tags "gaming,workstation" --scope "konsave,packages,flatpak,extra_config,extra_data"
# Tag’e göre restore (yalnızca konsave+extra-config)
python scripts/kde_backup_restore.py --restore --tag gaming --scope "konsave,extra_config"
# Timestamp ile verify/preview
python scripts/kde_backup_restore.py --verify 20250829-151354
python scripts/kde_backup_restore.py --preview --tag gaming
```

## Tag ve Scope
- `--tags "a,b,c"`: Full backup sırasında yedeğe etiket(ler) ekler. Bu etiketler `meta.json` içine yazılır.
- `--tag X`: Restore/preview/verify sırasında, etiketi `X` olan en son yedeği otomatik seçer.
- `--scope "konsave,packages,flatpak,extra_config,extra_data"`: Hangi bileşenlerin uygulanacağını belirtir.
  - Belirtmezseniz, `meta.json` içindeki scope kullanılır; o da yoksa tümü varsayılan olarak etkindir.
- `meta.json` örneği:
```json
{
  "created": "2025-08-29-151354",
  "profile": "20250829_kde",
  "tags": ["minimal", "gaming", "workstation"],
  "scope": {
    "konsave": true,
    "packages": true,
    "flatpak": false,
    "extra_config": true,
    "extra_data": true
  }
}
```

### Preview Modu
- `--preview [latest|<timestamp>]` restore öncesi planlanan değişiklikleri gösterir:
  - Paketlerde kurulacak/kaldırılabilir farklar
  - Flatpak eksikleri
  - `extra-config/` ve `extra-data/` altında yeni/üzerine yazılacak dosyalar (örnek listesi)
- Not: Preview sadece ne olacağını gösterir; dosya silme işlemi yapmaz.

#### Etkileşimli Menü (güncel)
```
1) Full Backup (konsave + packages + flatpak + extra-*)
2) Restore (konsave import/apply + opsiyonel extra-*)
3) Quick Backup (incremental extra-*)
4) Verify (son/ seçili yedekte .knsv içeriğini denetle)
5) Preview (önizleme)
6) Restore Dry-Run (simülasyon)
7) Compare (iki yedeği karşılaştır)
8) Import Bundle (paylaşılan profil klasörü)
9) Çıkış
```

### Konsave Argüman Passthrough
- `--konsave-args "..."` ile `konsave save/export` komutlarına ileri seviye argümanlar iletilebilir (konsave’in desteklediği ölçüde).
- Örnek (temsili):
```bash
python scripts/kde_backup_restore.py --full --konsave-args "--something plasma"
```
> Not: Argüman desteği `konsave` sürümünüzde değişebilir.

### Prompt'suz extra-* kopyalama bayrakları
Restore veya bundle import sırasında `extra-config` / `extra-data` için soruları bastırmak:
```bash
# Her ikisini de otomatik onayla
python scripts/kde_backup_restore.py --restore latest --yes-extra-all

# Sadece extra-config'i onayla, extra-data'yı sorma (hayır)
python scripts/kde_backup_restore.py --restore --tag gaming --yes-extra-config --no-extra-data

# Import bundle ile birlikte
python scripts/kde_backup_restore.py --import-bundle /path/to/bundle --scope "konsave,extra_config" --yes-extra-config
```
Desteklenen bayraklar:
- `--yes-extra-all`
- `--yes-extra-config` / `--no-extra-config`
- `--yes-extra-data` / `--no-extra-data`

## Otomasyon (systemd user timer)
Haftalık prompt’suz Quick Backup örneği (varsayılan konsave export=hayır):
1) `~/.config/systemd/user/kde-quick-backup.service`
```
[Unit]
Description=KDE Quick Backup (incremental)

[Service]
Type=oneshot
ExecStart=/usr/bin/env bash -lc 'printf "h\n" | python %h/path/to/repo/scripts/kde_backup_restore.py --quick'
```
2) `~/.config/systemd/user/kde-quick-backup.timer`
```
[Unit]
Description=Run KDE Quick Backup weekly

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=default.target
```
3) Etkinleştirme:
```bash
systemctl --user enable --now kde-quick-backup.timer
```

## Notlar
- Betik, paketleri **otomatik kurmaz**; komutları gösterir. İsterseniz otomatik kurulum seçeneği eklenebilir.
- Konsave ile yedek kapsamı `~/.config` ve `~/.local/share` altındaki KDE/Plasma dosyalarını kapsar.
- `extra-config/` ve `extra-data/` ile konsave dışı kritik dosyalar ve kullanıcı verileri de güvence altına alınır.

> “KDE ortamınız sadece bir masaüstü değil, üretkenliğinizin ve kimliğinizin dijital yansımasıdır. Bu araç, onu korumanız ve paylaşmanız için tasarlandı.”

---

## 📦 KDE’yi Yedeklemek Neden Önemlidir?
- **Felaket kurtarma**: Bozulan ayarları saniyeler içinde geri alın.
- **Taşınabilirlik**: Çoklu cihazda aynı KDE deneyimini yakalayın.
- **Deneysel çalışmalar**: Değişiklik yapmadan önce snapshot gibi yedek alın.

## 🧪 Restore Öncesi Preview ile Riskleri Azaltın
- `--preview [latest|<timestamp>|--tag X]` ile nelerin değişeceğini görün.
- Paket/flatpak farkları ve `extra-*`te yeni/değişen dosyaların özeti gösterilir.
- Silme işlemi yapılmadığı bilgisi net olarak belirtilir.

### 🔄 Restore Dry Run (Simülasyon)
Gerçek restore yerine adımları **simüle eder** ve yaklaşık boyut bilgisi verir.
```bash
python scripts/kde_backup_restore.py --dry-run latest
python scripts/kde_backup_restore.py --restore-dry-run --tag gaming --scope "konsave,extra_config"
```
- Konsave için sadece komut önizlemesi.
- Paket/flatpak için eksikler ve (varsa) yaklaşık toplam indirme boyutu tahmini.
- `extra-*` için rsync `--dry-run` benzeri `+` (yeni) / `~` (üzerine yaz) çıktısı.

## 🧠 Konsave Profilleri Nasıl Paylaşılır?
- `.knsv` dosyasını paylaşın; alıcı taraf `konsave -i` ve `konsave -a <profil>` ile uygular.
- `--konsave-args` ile tematik/filtreli profiller üretebilirsiniz (konsave sürümüne bağlıdır).

### 🌐 Topluluk Profili Paylaşım Formatı
Paylaşılabilir bir `profile_bundle/` dizini hazırlayın: `.knsv` + `meta.json` + (opsiyonel) `extra-*` + kısa `README.md`.
```bash
# Uygulama
python scripts/kde_backup_restore.py --import-bundle /path/to/profile_bundle --scope "konsave,extra_config"
```

## 🔄 KDE Ortamınızı Otomatik Güncel Tutun (systemd ile)
- README içindeki systemd user timer örneğini kullanın.
- Haftalık `--quick` ile hızlı ve küçük artımlı yedekler alın.

### 🧩 Yedek Karşılaştırma Modu
İki yedeğin farklarını gösterir (timestamp öneki, `latest` veya `tag:<isim>` desteklenir):
```bash
python scripts/kde_backup_restore.py --compare 20250829-151354 20250822-093012
python scripts/kde_backup_restore.py --compare latest tag:gaming
```
- Konsave arşiv girişlerindeki farkların özeti (isim listesi)
- Paket/flatpak değişimleri
- `extra-*` dosya farkları

## Topgrade + systemd Quick Backup
- __Topgrade pre_command__ ile haftalık/elle yükseltme öncesi hızlı yedek:
  `~/.config/topgrade.toml` içine ekleyin:
  ```toml
  [pre_commands]
  "KDE Quick Backup" = "bash -lc 'cd /mnt/ee8bf59b-815d-47bd-b440-5ba8ae82ff4a/projects/kde-profile-backup && printf \"h\\n\" | python3 scripts/kde_backup_restore.py --quick'"
  ```
  - `printf "h\n"` ile konsave export sorusuna otomatik "hayır" denir.
  - Yedek hedefi repo içindeki `kde-backups/latest/` klasörüdür (gitignore’dadır).

## systemd ile Haftalık Quick Backup (Cuma 20:00)
Kullanıcı servisi ve zamanlayıcı (user units):

1) `~/.config/systemd/user/kde-weekly-backup.service`
```ini
[Unit]
Description=Weekly KDE Profile Backup
After=graphical-session.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/projects/kde-profile-backup/scripts/kde_backup_restore.py --full
Environment=DISPLAY=:0
Environment=HOME=%h
WorkingDirectory=%h/projects/kde-profile-backup
StandardOutput=journal
StandardError=journal

# Add a small delay to ensure desktop is fully loaded
ExecStartPre=/bin/sleep 30
```

2) `~/.config/systemd/user/kde-weekly-backup.timer`
```ini
[Unit]
Description=Timer for weekly KDE profile backup
Requires=kde-weekly-backup.service

[Timer]
# Run weekly on Friday at 8:00 PM
OnCalendar=Fri *-*-* 20:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

3) Etkinleştirme ve kontrol:
```bash
# Dosyaları kopyalayın
mkdir -p ~/.config/systemd/user
cp /path/to/kde-weekly-backup.service ~/.config/systemd/user/
cp /path/to/kde-weekly-backup.timer ~/.config/systemd/user/

# Servisleri etkinleştirin ve başlatın
systemctl --user daemon-reload
systemctl --user enable --now kde-weekly-backup.timer

# Kontrol edin
systemctl --user status kde-weekly-backup.timer
journalctl --user -u kde-weekly-backup.service -f
```

## Haftalık Full Backup (konsave’li) — cron (oturum açıkken)
`konsave` etkileşim gerektirebildiği için full yedeklemeyi oturum açıkken cron ile zamanlamak pratik olabilir:
```bash
crontab -e
# Pazar 22:10 (örnek):
10 22 * * 0 cd /mnt/ee8bf59b-815d-47bd-b440-5ba8ae82ff4a/projects/kde-profile-backup && printf "\n" | python3 scripts/kde_backup_restore.py --full
```

## 🧹 Otomatik Yedek Temizleme
- Full ve quick backup işlemleri, sadece en son 3 yedeği koruyacak şekilde otomatik temizlik yapar
- Eski yedekler otomatik olarak silinir, disk alanı sorununu önler
- `cleanup_old_backups(keep_count=3)` fonksiyonu ile özelleştirilebilir

## 🌐 Geliştirilmiş Paket Desteği
- Full backup sırasında tüm sistem paketleri (AUR, Flatpak, pacman/dnf/apt/zypper) JSON formatında kaydedilir
- `system-packages.json` dosyasında tüm kaynaklardan paket listesi bulunur
- Tek tek formatlarda da paket listeleri (.txt dosyaları) tutulur

## 🔐 Güvenlik ve Yapılandırma Desteği
- SSH ve GPG anahtarları otomatik olarak yedeklenir
- Tarayıcı profilleri (Firefox, Brave, Chrome, Chromium) ve yapılandırmaları desteklenir
- MIME ilişkilendirmeleri (`~/.config/mimeapps.list`) ve otomatik başlatma uygulamaları (`~/.config/autostart/`) yedeklenir
- KDE Connect, Thunderbird gibi uygulamaların yapılandırmaları sadece varsa yedeklenir (gereksiz içerik eklenmez)

## 🧵 Topluluk Profilleri: Paylaşılabilir .knsv temaları ve restore senaryoları
- Yedeklerinizi `--tags` ile sınıflandırın: `minimal`, `gaming`, `workstation` vb.
- Restore sırasında `--tag gaming` gibi etiketlerle doğru yedeği seçin.
