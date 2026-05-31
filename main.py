#!/usr/bin/env python3
"""
TorBox - Tüm sistem trafiğini Tor üzerinden yönlendirir
"""

import logging
import os
import shutil
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    requests = None

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class TorTrafficRedirector:
    TOR_CHAIN = 'TORBOX'
    TOR_USER = 'tor'
    TORRC_MAIN = '/etc/tor/torrc'
    TORRC_CUSTOM = '/etc/tor/torrc.d/torbox.conf'

    def __init__(self):
        self.trans_port = 9040
        self.dns_port = 5353
        self.tor_socks = 9050
        self.excluded_networks = [
            '127.0.0.0/8',
            '192.168.0.0/16',
            '10.0.0.0/8',
            '172.16.0.0/12',
            '169.254.0.0/16',
        ]

    def check_root(self):
        if os.geteuid() != 0:
            logger.error('Bu script root olarak çalıştırılmalı: sudo torbox start')
            sys.exit(1)

    def check_command(self, command_name):
        return shutil.which(command_name) is not None

    def check_tor_running(self):
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', 'tor'],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip() == 'active'
        except Exception:
            return False

    def _run(self, args, check=True, **kwargs):
        return subprocess.run(args, capture_output=True, text=True, check=check, **kwargs)

    def chain_exists(self):
        result = subprocess.run(
            ['iptables', '-t', 'nat', '-L', self.TOR_CHAIN],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def output_jump_exists(self):
        result = subprocess.run(
            ['iptables', '-t', 'nat', '-C', 'OUTPUT', '-j', self.TOR_CHAIN],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def setup_iptables(self):
        try:
            tor_uid = subprocess.check_output(['id', '-u', self.TOR_USER], text=True).strip()
        except subprocess.CalledProcessError as exc:
            logger.error('Tor kullanıcısının UID bilgisi alınamadı: %s', exc)
            return False

        if not self.chain_exists():
            self._run(['iptables', '-t', 'nat', '-N', self.TOR_CHAIN], check=True)

        if not self.output_jump_exists():
            self._run(['iptables', '-t', 'nat', '-A', 'OUTPUT', '-j', self.TOR_CHAIN], check=True)

        rules = [
            ['-m', 'owner', '--uid-owner', tor_uid, '-j', 'RETURN'],
            ['-o', 'lo', '-j', 'RETURN'],
        ]
        rules += [['-d', net, '-j', 'RETURN'] for net in self.excluded_networks]
        rules += [
            ['-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', str(self.dns_port)],
            ['-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', str(self.dns_port)],
            ['-p', 'tcp', '-j', 'REDIRECT', '--to-ports', str(self.trans_port)],
        ]

        for rule in rules:
            args = ['iptables', '-t', 'nat', '-A', self.TOR_CHAIN] + rule
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            if result.returncode != 0 and 'File exists' not in result.stderr:
                logger.error('iptables kuralı eklenemedi: %s %s', ' '.join(args), result.stderr.strip())
                return False

        logger.info('✓ iptables kuralları başarıyla uygulandı')
        return True

    def clear_iptables(self):
        if self.output_jump_exists():
            subprocess.run(['iptables', '-t', 'nat', '-D', 'OUTPUT', '-j', self.TOR_CHAIN], check=False)

        if self.chain_exists():
            subprocess.run(['iptables', '-t', 'nat', '-F', self.TOR_CHAIN], check=False)
            subprocess.run(['iptables', '-t', 'nat', '-X', self.TOR_CHAIN], check=False)
            logger.info('✓ torbox zinciri kaldırıldı')
            return True

        logger.info('✔ iptables içinde torbox zinciri bulunamadı')
        return True

    def configure_tor(self):
        torrc_content = (
            '# Transparent Proxy için gerekli ayarlar\n'
            'VirtualAddrNetworkIPv4 10.192.0.0/10\n'
            'AutomapHostsOnResolve 1\n'
            'TransPort 9040\n'
            'DNSPort 5353\n'
            'SocksPort 9050\n'
            'ControlPort 9051\n'
            'CookieAuthentication 1\n'
        )

        current = ''
        if os.path.exists(self.TORRC_CUSTOM):
            with open(self.TORRC_CUSTOM, 'r') as f:
                current = f.read()

        if 'TransPort 9040' in current and 'DNSPort 5353' in current:
            logger.info('Tor yapılandırması zaten torbox için hazır')
            return True

        try:
            os.makedirs(os.path.dirname(self.TORRC_CUSTOM), exist_ok=True)
            with open(self.TORRC_CUSTOM, 'w') as f:
                f.write(torrc_content)
            logger.info('Tor için yeni konfigürasyon yazıldı: %s', self.TORRC_CUSTOM)

            self._run(['systemctl', 'restart', 'tor'], check=True)
            time.sleep(3)
            logger.info('✓ Tor yeniden başlatıldı')
            return True
        except Exception as exc:
            logger.error('Tor yapılandırma hatası: %s', exc)
            return False

    def test_connection(self):
        logger.info('Bağlantı test ediliyor...')

        if not self.check_command('curl'):
            logger.error('curl yüklü değil; test yapılamıyor')
            return False

        tests = [
            {
                'name': 'SOCKS5 Proxy',
                'command': ['curl', '--socks5-hostname', '127.0.0.1:9050', '-s', 'https://check.torproject.org/api/ip'],
            },
            {
                'name': 'Transparent Proxy',
                'command': ['curl', '-s', 'https://check.torproject.org/api/ip'],
            },
            {
                'name': 'DNS Kontrol',
                'command': ['curl', '-s', 'https://dnsleaktest.com/json'],
            },
        ]

        for test in tests:
            result = subprocess.run(test['command'], capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                logger.info('✓ %s: %s', test['name'], result.stdout.strip()[:100])
            else:
                logger.warning('✗ %s: %s', test['name'], result.stderr.strip() or 'Başarısız')

        if requests is None:
            logger.warning('requests modülü bulunamadı; Python tabanlı Tor testi atlandı')
            return True

        try:
            proxies = {
                'http': 'socks5h://127.0.0.1:9050',
                'https': 'socks5h://127.0.0.1:9050',
            }
            response = requests.get('https://check.torproject.org/api/ip', proxies=proxies, timeout=15)
            data = response.json()
            if data.get('IsTor'):
                logger.info('✓ Tor bağlantısı aktif - IP: %s', data.get('IP'))
                return True
            logger.warning('✗ Tor bağlantısı görünmüyor!')
            return False
        except Exception as exc:
            logger.error('Python Tor testi başarısız: %s', exc)
            return False

    def show_status(self):
        logger.info('%s', '=' * 50)
        logger.info('TORBOX DURUMU')
        logger.info('%s', '=' * 50)

        if self.chain_exists() and self.output_jump_exists():
            logger.info('✓ iptables torbox zinciri AKTİF')
        else:
            logger.info('✗ iptables torbox zinciri PASİF')

        if self.check_tor_running():
            logger.info('✓ Tor servisi ÇALIŞIYOR')
        else:
            logger.info('✗ Tor servisi ÇALIŞMIYOR')

        logger.info('%s', '=' * 50)

    def start(self):
        self.check_root()

        logger.info('TorBox başlatılıyor...')

        if not self.configure_tor():
            logger.error('Tor yapılandırılamadı!')
            return False

        if not self.check_tor_running():
            logger.info('Tor servisi başlatılıyor...')
            self._run(['systemctl', 'start', 'tor'], check=True)
            time.sleep(5)

        if not self.setup_iptables():
            logger.error('iptables kuralları uygulanamadı!')
            return False

        time.sleep(2)
        self.test_connection()

        logger.info('✓ TÜM TRAFİK TOR ÜZERİNDEN YÖNLENDİRİLİYOR')
        logger.info('Durdurmak için: sudo torbox stop')
        return True

    def stop(self):
        self.check_root()

        logger.info('TorBox durduruluyor...')
        self.clear_iptables()
        logger.info('✓ Trafik yönlendirme durduruldu')
        self.show_status()


def print_usage():
    print('Kullanım:')
    print('  sudo torbox start   - Tüm trafiği Tor üzerinden yönlendir')
    print('  sudo torbox stop    - Yönlendirmeyi durdur')
    print('  sudo torbox status  - Durumu göster')
    print('  sudo torbox test    - Bağlantıyı test et')


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()
    redirector = TorTrafficRedirector()

    if command == 'start':
        redirector.start()
    elif command == 'stop':
        redirector.stop()
    elif command == 'status':
        redirector.show_status()
    elif command == 'test':
        redirector.test_connection()
    else:
        print(f'Geçersiz komut: {command}')
        print_usage()


if __name__ == '__main__':
    main()
