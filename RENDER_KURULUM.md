# Poliçem — Render hazırlığı

Bu ZIP içindeki dosyalar depo köküne (ZIP olarak değil, açılmış dosyalar olarak) konulmalıdır. `static/index.html` eksik bırakılmamalıdır.

Render: Docker runtime, Dockerfile `./Dockerfile`, port `${PORT:-8000}`, health endpoint `/api/health`.

ZORUNLU: Güçlü ve gizli `POLICEM_SETUP_KEY` ortam değişkeni. SQLite ve yüklenen PDF'ler için `POLICEM_DATA=/var/lib/policem` yolunda kalıcı disk gerekir. Disk olmadan restart/deploy sonrasında veri kaybı olabilir.

Bu kaynak gerçek müşteri verileriyle kullanıma hazır değildir. Yetki izolasyonu, rate limiting, yedekleme, KVKK ve güvenlik denetimleri eksiktir. GitHub deposu public ise müşteri dosyalarını veya gizli anahtarları yüklemeyin.

Yerel test: `pytest -q tests/` (2026-10-15: 8 test geçti).
