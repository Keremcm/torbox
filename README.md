# TorBox

`TorBox`, Linux sisteminizde tüm çıkış trafiğini Tor üzerinden yönlendirmek için tasarlanmış basit bir araçtır. Bu proje `main.py` ve `install.sh` içerir;
`main.py` Tor yapılandırmasını ve `iptables` kurallarını yönetir, `install.sh` ise sisteminizde gerekli paketler varsa bunları yüklemeden kurarak `torbox` komutunu `/usr/local/bin/torbox` olarak oluşturur.

---

## İçindekiler

- [Özellikler](#özellikler)
- [Gereksinimler](#gereksinimler)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Nasıl çalışır](#nasıl-çalışır)
- [Yapılandırma](#yapılandırma)
- [Test ve doğrulama](#test-ve-doğrulama)
- [Durdurma](#durdurma)
- [Sorun giderme](#sorun-giderme)
- [Dağıtım uyumluluğu](#dağıtım-uyumluluğu)
- [Notlar](#notlar)

---

## Özellikler

- Tüm sistem çıkış trafiğini Tor üzerinden yönlendirme
- Tor yapılandırmasını `torrc.d/torbox.conf` dosyasına yazar
- `iptables` içinde özel bir zincir (`TORBOX`) kullanır
- Mevcut Tor sistem trafiğini halihazırda aşırı engellemeden korur
- `install.sh` ile `torbox` komutunu sistem genelinde kurma
- Paket yükleme sırasında mevcut paketleri yeniden yüklemeden sadece eksik olanları kurma

---

## Gereksinimler

- Linux
- `bash` destekli terminal
- `python3`
- `systemd` tabanlı servis yönetimi (`systemctl`)
- `tor`
- `curl`
- `iptables`
- `python3-requests` veya paket bağımlılığı olarak `requests`
- Root yetkisi

> `install.sh` bu paketleri tespit eder ve yalnızca eksik paketleri yükler. Paket veritabanlarını güncellemez.

---

## Kurulum

1. Depoyu indirin veya kopyalayın:

```bash
git clone <repo-url> torbox
cd torbox
```

2. `install.sh` betiğini çalıştırın:

```bash
sudo bash ./install.sh
```

3. Kurulumdan sonra komut şu şekilde kullanılabilir:

```bash
sudo torbox start
sudo torbox stop
sudo torbox status
sudo torbox test
```

---

## Kullanım

### Başlatma

TorBox'u başlatmak için:

```bash
sudo torbox start
```

Bu komut:

- root yetkisini doğrular
- Tor yapılandırmasını `TORRC_CUSTOM` dosyasına yazar
- Tor servisini başlatır veya yeniden başlatır
- `iptables` içinde `TORBOX` adlı özel bir zincir yaratır
- TCP ve DNS isteklerini Tor'a yönlendirir
- bağlantı testi çalıştırır

### Durdurma

Tor trafiğini normale döndürmek için:

```bash
sudo torbox stop
```

Bu komut:

- `TORBOX` zinciri için `OUTPUT` yönlendirmesini kaldırır
- `TORBOX` zincirini boşaltır ve siler
- mevcut durumu gösterir

### Durum

TorBox kurallarının aktifliğini kontrol etmek için:

```bash
sudo torbox status
```

### Test

Tor bağlantısını test etmek için:

```bash
sudo torbox test
```

Bu komut hem `curl` tabanlı hem de Python `requests` tabanlı kontrol çalıştırır (eğer `requests` yüklenmişse).

---

## Nasıl çalışır

`main.py` aşağıdaki adımları takip eder:

1. `TorTrafficRedirector` sınıfını oluşturur
2. `start` çağrıldığında:
   - yedek root kontrolü yapar
   - Tor yapılandırmasını günceller
   - Tor hizmetini başlatır
   - `iptables` içinde `TORBOX` zincirini oluşturur
   - tüm TCP trafiğini ve DNS trafiğini Tor portlarına yönlendirir
3. `stop` çağrıldığında:
   - `OUTPUT` zincirinden `TORBOX` yönlendirmesini kaldırır
   - `TORBOX` zincirini siler
4. `status` ve `test` komutları sistemsel durum hakkında bilgi verir

---

## Yapılandırma

Tor yapılandırması proje tarafından `/etc/tor/torrc.d/torbox.conf` dosyasına yazılır:

```text
# Transparent Proxy için gerekli ayarlar
VirtualAddrNetworkIPv4 10.192.0.0/10
AutomapHostsOnResolve 1
TransPort 9040
DNSPort 5353
SocksPort 9050
ControlPort 9051
CookieAuthentication 1
```

Bu dosya Tor servisini yeniden başlatırken otomatik olarak yüklenir.

---

## Test ve doğrulama

### Manuel doğrulama

TorBox çalıştıktan sonra aşağıdaki komutları kullanabilirsiniz:

```bash
curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org/api/ip
curl -s https://check.torproject.org/api/ip
```

İkinci komutta `Tor` IP adresi görmelisiniz. Eğer `requests` yüklüyse, `sudo torbox test` komutu da Tor üzerinden IP kontrolü yapar.

---

## Durdurma

TorBox trafiğini geri almanın güvenli yolu:

```bash
sudo torbox stop
```

Bu komut, oluşturulan `TORBOX` zincirini sistem `iptables` tablosundan siler. Diğer `nat` kurallarına dokunmaz.

---

## Sorun giderme

### `torbox` komutu bulunamıyor

- `install.sh` doğru çalıştıysa `/usr/local/bin/torbox` oluşturulmuş olmalıdır.
- Değilse, kurulum sonrası `ls -l /usr/local/bin/torbox` komutuyla dosyanın varlığını kontrol edin.

### `iptables-nft` yerine `iptables` çakışması

- `install.sh` mevcut paketleri yeniden kurmadan yalnızca eksik olanları yükler.
- Yine de, `pacman` kullanıcıları `iptables`/`iptables-nft` çakışmaları alabilir. Bu durumda sistemde zaten çalışan `iptables` paketini tercih edin.

### `requests` yoksa Python testi atlanıyor

- `main.py`, eğer `requests` yüklenmemişse `curl` tabanlı testle devam eder.
- `requests` yüklemek için `sudo apt install python3-requests` veya dağıtımınıza uygun paketi kullanın.

### Tor servisi başlamazsa

- `sudo systemctl status tor` ile hizmet durumunu kontrol edin.
- `sudo journalctl -u tor -n 50` ile hata kayıtlarını inceleyin.

---

## Desteklenen dağıtımlar

`install.sh` aşağıdaki paket yöneticilerini algılar ve destekler:

- `apt` (Ubuntu, Debian)
- `dnf` (Fedora, CentOS, AlmaLinux, Rocky Linux)
- `pacman` (Arch, Manjaro)
- `zypper` (openSUSE, SLES)
- `apk` (Alpine)

---

## Notlar

- Bu proje `root` yetkisi gerektirir.
- `install.sh` paket veritabanını güncellemez; yalnızca mevcut veritabanından eksik paketleri yükler.
- TorBox, tüm TCP ve DNS trafiğinizi Tor ağından geçirir; bağlantı güvenliğini artırmak için sistem ve uygulama yapılandırmanızın Tor uyumlu olduğundan emin olun.
- Bu araç özel bir `iptables` zinciri kullandığı için mevcut diğer `nat` yapılandırmalarınıza doğrudan müdahale etmez.

---

## Lisans

Bu proje için lisans bilgisi burada belirtilmemiştir. Kullanmak istediğiniz lisansı eklemek için `LICENSE` dosyası oluşturabilirsiniz.
