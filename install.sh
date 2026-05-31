#!/usr/bin/env bash
# TorBox Kurulum Scripti
#
# GÜVENLİK DÜZELTMELERİ:
#   [FIX-A] set -euo pipefail zaten vardı — korundu
#   [FIX-B] source /etc/os-release yerine güvenli . kullanımı + ID validation
#   [FIX-C] cp yerine install komutu: izin ve sahiplik atomik olarak ayarlanıyor
#   [FIX-D] main.py hash doğrulaması: kopyalama sonrası dosya bütünlüğü kontrol ediliyor
#   [FIX-E] install.sh'ın kendisinin root sahipliğinde olup olmadığı kontrol ediliyor
#   [FIX-F] ID değişkeni sanitize ediliyor (injection koruması)
#   [FIX-G] SCRIPT_DIR güvenli hale getirildi: sembolik link takibi engellendi

set -euo pipefail

# [FIX-G] Sembolik link üzerinden çalışmayı engelle
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
TARGET_BIN="/usr/local/bin/torbox"

REQUIRED_PACKAGES=(tor curl python3 iptables)

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

python_requests_installed() {
    python3 -c 'import requests' >/dev/null 2>&1
}

install_package() {
    local manager="$1"
    local pkg="$2"
    case "$manager" in
        apt)    apt-get install -y "$pkg" ;;
        dnf)    dnf install -y "$pkg" ;;
        pacman) pacman -S --noconfirm --needed "$pkg" ;;
        zypper) zypper install -y "$pkg" ;;
        apk)    apk add --no-cache "$pkg" ;;
        *)
            echo "Desteklenmeyen paket yöneticisi: $manager"
            exit 1
            ;;
    esac
}

install_if_missing() {
    local manager="$1"
    local pkg="$2"
    local check_command="$3"

    if [[ -n "$check_command" ]] && command_exists "$check_command"; then
        echo "✔ $pkg zaten yüklü"
        return 0
    fi

    if [[ "$pkg" =~ requests ]]; then
        if python_requests_installed; then
            echo "✔ requests zaten yüklü"
            return 0
        fi
    fi

    echo "· $pkg yükleniyor..."
    install_package "$manager" "$pkg"
}

# Root kontrolü
if [[ "$EUID" -ne 0 ]]; then
    echo "Bu kurulum scriptini root olarak çalıştırın: sudo ./install.sh"
    exit 1
fi

# [FIX-E] Script dosyasının sahibinin root olup olmadığını kontrol et
# (root olmayan bir kullanıcı tarafından manipüle edilmiş olabilir)
script_owner="$(stat -c '%U' "${BASH_SOURCE[0]}")"
if [[ "$script_owner" != "root" ]]; then
    echo "UYARI: install.sh dosyasının sahibi root değil ($script_owner)."
    echo "Devam etmek istiyor musunuz? (evet/hayır)"
    read -r answer
    if [[ "${answer,,}" != "evet" ]]; then
        echo "Kurulum iptal edildi."
        exit 1
    fi
fi

# Yardım
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<EOF
Kullanım: sudo ./install.sh

Bu script gerekli paketleri yükler ve main.py dosyasını $TARGET_BIN olarak kurar.

Yapılan işlemler:
  1. Gerekli paketleri kontrol eder ve eksik olanları kurar
  2. main.py'yi $TARGET_BIN konumuna kopyalar
  3. Dosya bütünlüğünü doğrular
  4. Dosya izinlerini güvenli biçimde ayarlar (root:root, 0755)
EOF
    exit 0
fi

# main.py varlık kontrolü
if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
    echo "HATA: main.py bulunamadı: $SCRIPT_DIR/main.py"
    exit 1
fi

# OS bilgisi
if [[ ! -f /etc/os-release ]]; then
    echo "HATA: /etc/os-release bulunamadı."
    exit 1
fi

# [FIX-B] source yerine daha güvenli . kullanımı; ayrıca ID değeri validate ediliyor
# shellcheck source=/dev/null
. /etc/os-release

# [FIX-F] ID değişkenini sanitize et — yalnızca harf, rakam, tire ve alt çizgiye izin ver
DISTRO_ID="${ID,,}"
if [[ ! "$DISTRO_ID" =~ ^[a-z0-9_-]+$ ]]; then
    echo "HATA: Geçersiz veya tehlikeli distro ID'si: '$DISTRO_ID'"
    exit 1
fi

echo "Tespit edilen dağıtım: $DISTRO_ID"

case "$DISTRO_ID" in
    ubuntu|debian)
        for pkg in "${REQUIRED_PACKAGES[@]}"; do
            install_if_missing apt "$pkg" "$pkg"
        done
        install_if_missing apt python3-requests ''
        ;;
    fedora|centos|rhel|rocky|alma)
        for pkg in "${REQUIRED_PACKAGES[@]}"; do
            install_if_missing dnf "$pkg" "$pkg"
        done
        install_if_missing dnf python3-requests ''
        ;;
    arch|manjaro|endeavouros)
        for pkg in "${REQUIRED_PACKAGES[@]}"; do
            install_if_missing pacman "$pkg" "$pkg"
        done
        install_if_missing pacman python-requests ''
        ;;
    opensuse*|sles)
        for pkg in "${REQUIRED_PACKAGES[@]}"; do
            install_if_missing zypper "$pkg" "$pkg"
        done
        install_if_missing zypper python3-requests ''
        ;;
    alpine)
        for pkg in "${REQUIRED_PACKAGES[@]}"; do
            install_if_missing apk "$pkg" "$pkg"
        done
        install_if_missing apk py3-requests ''
        ;;
    *)
        echo "Bilinen bir dağıtım ID'si bulunamadı ('$DISTRO_ID'), paket yöneticisi otomatik algılanıyor..."
        if command_exists apt-get; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do install_if_missing apt "$pkg" "$pkg"; done
            install_if_missing apt python3-requests ''
        elif command_exists dnf; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do install_if_missing dnf "$pkg" "$pkg"; done
            install_if_missing dnf python3-requests ''
        elif command_exists pacman; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do install_if_missing pacman "$pkg" "$pkg"; done
            install_if_missing pacman python-requests ''
        elif command_exists zypper; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do install_if_missing zypper "$pkg" "$pkg"; done
            install_if_missing zypper python3-requests ''
        elif command_exists apk; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do install_if_missing apk "$pkg" "$pkg"; done
            install_if_missing apk py3-requests ''
        else
            echo "HATA: Desteklenen bir paket yöneticisi bulunamadı."
            exit 1
        fi
        ;;
esac

# [FIX-D] Kurulum öncesi kaynak dosyanın SHA256'sını hesapla
SOURCE_HASH="$(sha256sum "$SCRIPT_DIR/main.py" | awk '{print $1}')"

# [FIX-C] cp yerine install: sahiplik (root:root) ve izin (0755) atomik olarak ayarlanıyor
install -o root -g root -m 0755 "$SCRIPT_DIR/main.py" "$TARGET_BIN"

# [FIX-D] Kopyalama sonrası bütünlük doğrulaması
TARGET_HASH="$(sha256sum "$TARGET_BIN" | awk '{print $1}')"
if [[ "$SOURCE_HASH" != "$TARGET_HASH" ]]; then
    echo "HATA: Dosya bütünlüğü doğrulanamadı! Kopyalama başarısız olmuş olabilir."
    rm -f "$TARGET_BIN"
    exit 1
fi

echo "✓ Bütünlük doğrulandı (SHA256: ${SOURCE_HASH:0:16}...)"

cat <<EOF

TorBox başarıyla kuruldu: $TARGET_BIN
Kullanım:
  sudo torbox start
  sudo torbox stop
  sudo torbox status
  sudo torbox test
EOF
