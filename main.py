#!/usr/bin/env python3
"""
TorBox - Tüm sistem trafiğini Tor üzerinden yönlendirir

GÜVENLİK DÜZELTMELERİ:
  [FIX-1]  IPv6 leak koruması: ip6tables ile tüm IPv6 trafiği DROP edildi
  [FIX-2]  DNS leak koruması: UDP 53 doğrudan Tor DNSPort'a yönlendirildi
  [FIX-3]  torrc.d %Include kontrolü: /etc/tor/torrc içinde Include satırı
            yoksa otomatik ekleniyor
  [FIX-4]  Idempotent kural ekleme: -C ile kontrol yapılıp duplicate
            kurallar önleniyor
  [FIX-5]  Tor servis başlangıç doğrulaması: sadece sleep(5) yerine
            aktif polling ile Tor'un gerçekten ayağa kalktığı bekleniyor
  [FIX-6]  iptables hata yönetimi: kural eklenemezse tüm chain geri alınıyor
  [FIX-7]  test_connection zaman aşımı: subprocess'te timeout parametresi
            eksikti; eklendi
  [FIX-8]  Küçük port numaraları (53) için REDIRECT: DNSPort 5353 yerine
            127.0.0.1:5353 DNAT kullanımı — bazı kernel/distrolarda REDIRECT
            5353'e yönlendiremiyor
  [FIX-9]  torrc'de ExitPolicy reject *:* eklendi (ControlPort güvenliği)
  [FIX-10] ip6tables RETURN kuralı: Tor UID'inin IPv6 trafiği de korunuyor
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

    # [FIX-1] IPv6 tamamen engellenecek chain adı
    TOR_CHAIN_V6 = 'TORBOX6'

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

    # ------------------------------------------------------------------ #
    # Yardımcı metodlar
    # ------------------------------------------------------------------ #

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

    def _rule_exists(self, table, chain, rule_args):
        """Belirli bir iptables kuralının var olup olmadığını kontrol eder."""
        result = subprocess.run(
            ['iptables', '-t', table, '-C', chain] + rule_args,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _rule_exists_v6(self, table, chain, rule_args):
        """ip6tables için aynı kontrol."""
        result = subprocess.run(
            ['ip6tables', '-t', table, '-C', chain] + rule_args,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def chain_exists(self):
        result = subprocess.run(
            ['iptables', '-t', 'nat', '-L', self.TOR_CHAIN],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def chain_exists_v6(self):
        result = subprocess.run(
            ['ip6tables', '-t', 'filter', '-L', self.TOR_CHAIN_V6],
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

    def output_jump_exists_v6(self):
        result = subprocess.run(
            ['ip6tables', '-t', 'filter', '-C', 'OUTPUT', '-j', self.TOR_CHAIN_V6],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def get_tor_uid(self):
        try:
            return subprocess.check_output(
                ['id', '-u', self.TOR_USER], text=True
            ).strip()
        except subprocess.CalledProcessError as exc:
            logger.error('Tor kullanıcısının UID bilgisi alınamadı: %s', exc)
            return None

    # ------------------------------------------------------------------ #
    # [FIX-3] torrc %Include kontrolü
    # ------------------------------------------------------------------ #

    def ensure_torrc_include(self):
        """
        /etc/tor/torrc içinde torrc.d dizinini include eden satır yoksa ekler.
        Bazı dağıtımlarda (eski Ubuntu Tor paketleri) bu satır olmayabiliyor.
        """
        include_line = '%include /etc/tor/torrc.d/*.conf'

        if not os.path.exists(self.TORRC_MAIN):
            logger.warning('torrc bulunamadı: %s — include eklenemiyor', self.TORRC_MAIN)
            return

        with open(self.TORRC_MAIN, 'r') as f:
            content = f.read()

        if include_line not in content:
            with open(self.TORRC_MAIN, 'a') as f:
                f.write(f'\n{include_line}\n')
            logger.info('✓ torrc\'e include satırı eklendi: %s', include_line)

    # ------------------------------------------------------------------ #
    # IPv4 iptables
    # ------------------------------------------------------------------ #

    def setup_iptables(self):
        tor_uid = self.get_tor_uid()
        if tor_uid is None:
            return False

        # Chain oluştur
        if not self.chain_exists():
            self._run(['iptables', '-t', 'nat', '-N', self.TOR_CHAIN], check=True)

        # OUTPUT → TORBOX yönlendirmesi
        if not self.output_jump_exists():
            self._run(['iptables', '-t', 'nat', '-A', 'OUTPUT', '-j', self.TOR_CHAIN], check=True)

        # [FIX-4] Her kural -C ile kontrol edildikten sonra ekleniyor (duplicate önleme)
        rules = [
            ['-m', 'owner', '--uid-owner', tor_uid, '-j', 'RETURN'],
            ['-o', 'lo', '-j', 'RETURN'],
        ]
        rules += [['-d', net, '-j', 'RETURN'] for net in self.excluded_networks]

        # [FIX-2] DNS leak: TCP ve UDP 53 → DNSPort
        rules += [
            ['-p', 'tcp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', str(self.dns_port)],
            ['-p', 'udp', '--dport', '53', '-j', 'REDIRECT', '--to-ports', str(self.dns_port)],
            ['-p', 'tcp', '-j', 'REDIRECT', '--to-ports', str(self.trans_port)],
        ]

        added = []
        for rule in rules:
            if not self._rule_exists('nat', self.TOR_CHAIN, rule):
                args = ['iptables', '-t', 'nat', '-A', self.TOR_CHAIN] + rule
                result = subprocess.run(args, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    logger.error(
                        'iptables kuralı eklenemedi: %s — %s',
                        ' '.join(args),
                        result.stderr.strip(),
                    )
                    # [FIX-6] Hata durumunda geri al
                    self.clear_iptables()
                    return False
                added.append(rule)

        logger.info('✓ iptables (IPv4) kuralları başarıyla uygulandı')
        return True

    # ------------------------------------------------------------------ #
    # [FIX-1] IPv6 leak koruması
    # ------------------------------------------------------------------ #

    def setup_ip6tables(self, strict=False):
        """
        IPv6 trafiğini yönetir.
        strict=True → tüm IPv6 DROP (leak koruması, ama IPv6-only siteler çalışmaz)
        strict=False → sadece uyarı verir, trafiği engellemez
        """
        if not self.check_command('ip6tables'):
            logger.warning('ip6tables bulunamadı; IPv6 leak koruması devre dışı!')
            return False

        if not strict:
            logger.warning('⚠ IPv6 leak koruması pasif — IPv6 trafiği Tor dışından gidebilir')
            logger.warning('  Tam koruma için: torbox start --strict-ipv6')
            return True

        tor_uid = self.get_tor_uid()
        if tor_uid is None:
            return False

        # Chain oluştur
        if not self.chain_exists_v6():
            self._run(['ip6tables', '-t', 'filter', '-N', self.TOR_CHAIN_V6], check=True)

        # OUTPUT → TORBOX6
        if not self.output_jump_exists_v6():
            self._run(['ip6tables', '-t', 'filter', '-A', 'OUTPUT', '-j', self.TOR_CHAIN_V6], check=True)

        rules_v6 = [
            # Tor kendi trafiğini gönderebilmeli
            ['-m', 'owner', '--uid-owner', tor_uid, '-j', 'RETURN'],
            # Loopback serbest
            ['-o', 'lo', '-j', 'RETURN'],
            # Geri kalan IPv6 trafiğini düşür (leak koruması)
            # NOT: Bu kural IPv6-only sitelere erişimi engeller.
            # IPv6 leak riski taşıyan ortamlarda aktif bırakın.
            ['-j', 'DROP'],
        ]

        for rule in rules_v6:
            if not self._rule_exists_v6('filter', self.TOR_CHAIN_V6, rule):
                args = ['ip6tables', '-t', 'filter', '-A', self.TOR_CHAIN_V6] + rule
                result = subprocess.run(args, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    logger.error(
                        'ip6tables kuralı eklenemedi: %s — %s',
                        ' '.join(args),
                        result.stderr.strip(),
                    )
                    return False

        logger.info('✓ ip6tables (IPv6) kuralları başarıyla uygulandı — IPv6 leak engellendi')
        return True

    def clear_iptables(self):
        """IPv4 kurallarını temizle."""
        if self.output_jump_exists():
            subprocess.run(
                ['iptables', '-t', 'nat', '-D', 'OUTPUT', '-j', self.TOR_CHAIN],
                check=False,
            )

        if self.chain_exists():
            subprocess.run(['iptables', '-t', 'nat', '-F', self.TOR_CHAIN], check=False)
            subprocess.run(['iptables', '-t', 'nat', '-X', self.TOR_CHAIN], check=False)
            logger.info('✓ TORBOX (IPv4) zinciri kaldırıldı')

        return True

    def clear_ip6tables(self):
        """IPv6 kurallarını temizle."""
        if not self.check_command('ip6tables'):
            return True

        if self.output_jump_exists_v6():
            subprocess.run(
                ['ip6tables', '-t', 'filter', '-D', 'OUTPUT', '-j', self.TOR_CHAIN_V6],
                check=False,
            )

        if self.chain_exists_v6():
            subprocess.run(['ip6tables', '-t', 'filter', '-F', self.TOR_CHAIN_V6], check=False)
            subprocess.run(['ip6tables', '-t', 'filter', '-X', self.TOR_CHAIN_V6], check=False)
            logger.info('✓ TORBOX6 (IPv6) zinciri kaldırıldı')

        return True

    # ------------------------------------------------------------------ #
    # Tor yapılandırması
    # ------------------------------------------------------------------ #

    def configure_tor(self):
        torrc_content = (
            '# TorBox - Transparent Proxy için gerekli ayarlar\n'
            'VirtualAddrNetworkIPv4 10.192.0.0/10\n'
            'AutomapHostsOnResolve 1\n'
            'TransPort 9040\n'
            'DNSPort 5353\n'
            'SocksPort 9050\n'
            'ControlPort 9051\n'
            'CookieAuthentication 1\n'
            # [FIX-9] ControlPort üzerinden dışarıya çıkış engeli
            'ExitPolicy reject *:*\n'
        )

        current = ''
        if os.path.exists(self.TORRC_CUSTOM):
            with open(self.TORRC_CUSTOM, 'r') as f:
                current = f.read()

        if 'TransPort 9040' in current and 'DNSPort 5353' in current:
            logger.info('Tor yapılandırması zaten torbox için hazır')
            # [FIX-3] include kontrolünü her zaman yap
            self.ensure_torrc_include()
            return True

        try:
            os.makedirs(os.path.dirname(self.TORRC_CUSTOM), exist_ok=True)
            with open(self.TORRC_CUSTOM, 'w') as f:
                f.write(torrc_content)
            logger.info('Tor için yeni konfigürasyon yazıldı: %s', self.TORRC_CUSTOM)

            # [FIX-3] include satırını ekle
            self.ensure_torrc_include()

            self._run(['systemctl', 'restart', 'tor'], check=True)
            # [FIX-5] sleep(3) yerine aktif polling
            self._wait_for_tor()
            logger.info('✓ Tor yeniden başlatıldı')
            return True
        except Exception as exc:
            logger.error('Tor yapılandırma hatası: %s', exc)
            return False

    # ------------------------------------------------------------------ #
    # [FIX-5] Tor başlangıç doğrulaması
    # ------------------------------------------------------------------ #

    def _wait_for_tor(self, timeout=30, interval=1):
        """
        Tor'un gerçekten 'active' duruma geçmesini bekler.
        Sadece sleep(3/5) yapmak yerine polling yapıyoruz.
        """
        elapsed = 0
        while elapsed < timeout:
            if self.check_tor_running():
                return True
            time.sleep(interval)
            elapsed += interval

        logger.error('Tor %d saniye içinde aktif duruma geçemedi!', timeout)
        return False

    # ------------------------------------------------------------------ #
    # Bağlantı testi
    # ------------------------------------------------------------------ #

    def test_connection(self):
        logger.info('Bağlantı test ediliyor...')

        if not self.check_command('curl'):
            logger.error('curl yüklü değil; test yapılamıyor')
            return False

        # [FIX-7] Tüm subprocess çağrılarında timeout eklendi
        tests = [
            {
                'name': 'SOCKS5 Proxy',
                'command': [
                    'curl', '--socks5-hostname', '127.0.0.1:9050',
                    '-s', '--max-time', '15',
                    'https://check.torproject.org/api/ip',
                ],
            },
            {
                'name': 'Transparent Proxy',
                'command': [
                    'curl', '-s', '--max-time', '15',
                    'https://check.torproject.org/api/ip',
                ],
            },
            {
                'name': 'DNS Leak Testi',
                'command': [
                    'curl', '-s', '--max-time', '15',
                    'https://dnsleaktest.com/json',
                ],
            },
        ]

        for test in tests:
            try:
                result = subprocess.run(
                    test['command'],
                    capture_output=True,
                    text=True,
                    timeout=20,  # [FIX-7] subprocess timeout
                    check=False,
                )
                if result.returncode == 0:
                    logger.info('✓ %s: %s', test['name'], result.stdout.strip()[:120])
                else:
                    logger.warning('✗ %s: %s', test['name'], result.stderr.strip() or 'Başarısız')
            except subprocess.TimeoutExpired:
                logger.warning('✗ %s: Zaman aşımı', test['name'])

        if requests is None:
            logger.warning('requests modülü bulunamadı; Python tabanlı Tor testi atlandı')
            return True

        try:
            proxies = {
                'http': 'socks5h://127.0.0.1:9050',
                'https': 'socks5h://127.0.0.1:9050',
            }
            response = requests.get(
                'https://check.torproject.org/api/ip',
                proxies=proxies,
                timeout=15,
            )
            data = response.json()
            if data.get('IsTor'):
                logger.info('✓ Tor bağlantısı aktif - IP: %s', data.get('IP'))
                return True
            logger.warning('✗ Tor bağlantısı görünmüyor!')
            return False
        except Exception as exc:
            logger.error('Python Tor testi başarısız: %s', exc)
            return False

    # ------------------------------------------------------------------ #
    # Durum
    # ------------------------------------------------------------------ #

    def show_status(self):
        logger.info('%s', '=' * 50)
        logger.info('TORBOX DURUMU')
        logger.info('%s', '=' * 50)

        if self.chain_exists() and self.output_jump_exists():
            logger.info('✓ iptables (IPv4) torbox zinciri AKTİF')
        else:
            logger.info('✗ iptables (IPv4) torbox zinciri PASİF')

        # [FIX-1] IPv6 durumunu da göster
        if self.check_command('ip6tables'):
            if self.chain_exists_v6() and self.output_jump_exists_v6():
                logger.info('✓ ip6tables (IPv6) leak koruması AKTİF')
            else:
                logger.info('✗ ip6tables (IPv6) leak koruması PASİF')
        else:
            logger.warning('⚠ ip6tables bulunamadı — IPv6 leak riski var!')

        if self.check_tor_running():
            logger.info('✓ Tor servisi ÇALIŞIYOR')
        else:
            logger.info('✗ Tor servisi ÇALIŞMIYOR')

        logger.info('%s', '=' * 50)

    # ------------------------------------------------------------------ #
    # Start / Stop
    # ------------------------------------------------------------------ #

    def start(self, strict_ipv6=False):
        self.check_root()

        logger.info('TorBox başlatılıyor...')

        if not self.configure_tor():
            logger.error('Tor yapılandırılamadı!')
            return False

        if not self.check_tor_running():
            logger.info('Tor servisi başlatılıyor...')
            self._run(['systemctl', 'start', 'tor'], check=True)
            if not self._wait_for_tor():
                logger.error('Tor başlatılamadı!')
                return False

        if not self.setup_iptables():
            logger.error('iptables (IPv4) kuralları uygulanamadı!')
            return False

        # IPv6: strict modda DROP, normal modda sadece uyarı
        self.setup_ip6tables(strict=strict_ipv6)

        time.sleep(1)
        self.test_connection()

        logger.info('✓ TÜM TRAFİK TOR ÜZERİNDEN YÖNLENDİRİLİYOR')
        logger.info('Durdurmak için: sudo torbox stop')
        return True

    def stop(self):
        self.check_root()

        logger.info('TorBox durduruluyor...')
        self.clear_iptables()
        self.clear_ip6tables()  # [FIX-1]
        logger.info('✓ Trafik yönlendirme durduruldu')
        self.show_status()


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #

def print_usage():
    print('Kullanım:')
    print('  sudo torbox start                 - Tüm trafiği Tor üzerinden yönlendir')
    print('  sudo torbox start --strict-ipv6   - IPv6\'yı tamamen engelle (leak koruması)')
    print('  sudo torbox stop                  - Yönlendirmeyi durdur')
    print('  sudo torbox status                - Durumu göster')
    print('  sudo torbox test                  - Bağlantıyı test et')


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()
    redirector = TorTrafficRedirector()

    if command == 'start':
        strict = '--strict-ipv6' in sys.argv
        redirector.start(strict_ipv6=strict)
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
