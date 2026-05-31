#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
        apt)
            apt install -y "$pkg"
            ;;
        dnf)
            dnf install -y "$pkg"
            ;;
        pacman)
            pacman -S --noconfirm --needed "$pkg"
            ;;
        zypper)
            zypper install -y "$pkg"
            ;;
        apk)
            apk add --no-cache "$pkg"
            ;;
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

if [[ "$EUID" -ne 0 ]]; then
    echo "Bu kurulum scriptini root olarak çalıştırın: sudo ./install.sh"
    exit 1
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<EOF
Kullanım: sudo ./install.sh

Bu script gerekli paketleri yükler ve main.py dosyasını /usr/local/bin/torbox olarak kurar.
EOF
    exit 0
fi

if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
    echo "main.py bulunamadı: $SCRIPT_DIR/main.py"
    exit 1
fi

if [[ -f /etc/os-release ]]; then
    source /etc/os-release
else
    echo "OS bilgisi /etc/os-release içinde bulunamadı."
    exit 1
fi

case "${ID,,}" in
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
    arch|manjaro)
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
        if command -v apt >/dev/null 2>&1; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do
                install_if_missing apt "$pkg" "$pkg"
            done
            install_if_missing apt python3-requests ''
        elif command -v dnf >/dev/null 2>&1; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do
                install_if_missing dnf "$pkg" "$pkg"
            done
            install_if_missing dnf python3-requests ''
        elif command -v pacman >/dev/null 2>&1; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do
                install_if_missing pacman "$pkg" "$pkg"
            done
            install_if_missing pacman python-requests ''
        elif command -v zypper >/dev/null 2>&1; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do
                install_if_missing zypper "$pkg" "$pkg"
            done
            install_if_missing zypper python3-requests ''
        elif command -v apk >/dev/null 2>&1; then
            for pkg in "${REQUIRED_PACKAGES[@]}"; do
                install_if_missing apk "$pkg" "$pkg"
            done
            install_if_missing apk py3-requests ''
        else
            echo "Bu dağıtımda otomatik paket yükleme desteklenmiyor."
            exit 1
        fi
        ;;
esac

cp "$SCRIPT_DIR/main.py" "$TARGET_BIN"
chmod +x "$TARGET_BIN"

cat <<EOF
TorBox başarıyla kuruldu: $TARGET_BIN
Kullanım:
  sudo torbox start
  sudo torbox stop
  sudo torbox status
  sudo torbox test
EOF
