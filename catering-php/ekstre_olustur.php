<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$musteri_id = (int)($_POST['musteri_id'] ?? $_GET['musteri_id'] ?? 0);

$stmt = $pdo->prepare("SELECT * FROM musteriler WHERE id = ?");
$stmt->execute([$musteri_id]);
$musteri = $stmt->fetch();

if (!$musteri) {
    die('Müşteri bulunamadı. <a href="musteriler.php">Müşteri listesine dön</a>');
}

$adim = $_POST['adim'] ?? '';
$hata = '';
$oneri = null;
$kdv_orani = !empty($musteri['faturali_mi']) ? 10.0 : 0.0;

// ---------------------------------------------------------------
// ADIM 1 -> hesapla: girilen tarih aralığına göre sistemden öneri
// değerleri (fiili yemek tutarları, önceki bakiye, alınan avans)
// hesaplanır. Yemek adetleri günlük girişlerden alınır; PDF ekranında
// yeniden girilmez.
// ---------------------------------------------------------------
if ($adim === 'hesapla') {
    $baslangic = $_POST['baslangic_tarihi'] ?? '';
    $bitis     = $_POST['bitis_tarihi'] ?? '';
    if (!gecerli_tarih_mi($baslangic) || !gecerli_tarih_mi($bitis) || strtotime($bitis) < strtotime($baslangic)) {
        $hata = 'Lütfen geçerli bir başlama ve bitiş tarihi giriniz (bitiş, başlangıçtan önce olamaz).';
    } else {
        // Sistemdeki günlük girişlerden bu döneme ait fiili toplamlar.
        // Tutarlar da günlük kaydın yapıldığı andaki fiyat üzerinden gelir;
        // müşteri fiyatı sonradan değişse bile geçmiş ekstre doğru kalır.
        $stmt = $pdo->prepare("
            SELECT COALESCE(SUM(yemek_adedi),0) AS normal_adet,
                   COALESCE(SUM(gunluk_toplam_tutar),0) AS normal_tutar,
                   COALESCE(SUM(mesai_yemek_adedi),0) AS mesai_adet,
                   COALESCE(SUM(mesai_toplam_tutar),0) AS mesai_tutar
            FROM gunluk_yemek_verileri
            WHERE musteri_id = ? AND tarih BETWEEN ? AND ?
        ");
        $stmt->execute([$musteri_id, $baslangic, $bitis]);
        $giris_ozet = $stmt->fetch();

        // Önceki bakiye: başlangıç tarihinden ÖNCEKİ tüm hizmet - tüm tahsilat
        $stmt = $pdo->prepare("
            SELECT COALESCE(SUM(gunluk_toplam_tutar),0) + COALESCE(SUM(mesai_toplam_tutar),0) AS t
            FROM gunluk_yemek_verileri WHERE musteri_id = ? AND tarih < ?
        ");
        $stmt->execute([$musteri_id, $baslangic]);
        $onceki_hizmet = (float)$stmt->fetch()['t'];

        $stmt = $pdo->prepare("SELECT COALESCE(SUM(tutar),0) t FROM tahsilatlar WHERE musteri_id = ? AND tarih < ?");
        $stmt->execute([$musteri_id, $baslangic]);
        $onceki_tahsilat = (float)$stmt->fetch()['t'];

        // Faturalı müşterilerde geçmiş hizmet tutarları da %10 KDV ile
        // devir bakiyesine yansır. Faturasız müşterinin hesabı değişmez.
        $onceki_bakiye_oto = (float)$musteri['devreden_borc'] + $onceki_hizmet * (1 + $kdv_orani / 100) - $onceki_tahsilat;

        // Bu dönem içinde yapılan ödemeler (alınan avans önerisi)
        $stmt = $pdo->prepare("SELECT COALESCE(SUM(tutar),0) t FROM tahsilatlar WHERE musteri_id = ? AND tarih BETWEEN ? AND ?");
        $stmt->execute([$musteri_id, $baslangic, $bitis]);
        $avans_oto = (float)$stmt->fetch()['t'];

        $oneri = [
            'baslangic' => $baslangic,
            'bitis' => $bitis,
            'normal_adet_giris' => (int)$giris_ozet['normal_adet'],
            'normal_tutar_giris' => (float)$giris_ozet['normal_tutar'],
            'mesai_adet_giris' => (int)$giris_ozet['mesai_adet'],
            'mesai_tutar_giris' => (float)$giris_ozet['mesai_tutar'],
            'ara_toplam' => (float)$giris_ozet['normal_tutar'] + (float)$giris_ozet['mesai_tutar'],
            'kdv_orani' => $kdv_orani,
            'kdv_tutari' => ((float)$giris_ozet['normal_tutar'] + (float)$giris_ozet['mesai_tutar']) * $kdv_orani / 100,
            'onceki_bakiye_oto' => $onceki_bakiye_oto,
            'avans_oto' => $avans_oto,
        ];
    }
}

// ---------------------------------------------------------------
// ADIM 2 -> olustur: son düzenlenmiş değerler kaydedilir ve PDF'e
// yönlendirilir.
// ---------------------------------------------------------------
if ($adim === 'olustur') {
    $baslangic = $_POST['baslangic_tarihi'] ?? '';
    $bitis = $_POST['bitis_tarihi'] ?? '';
    if (!gecerli_tarih_mi($baslangic) || !gecerli_tarih_mi($bitis) || strtotime($bitis) < strtotime($baslangic)) {
        die('Geçersiz ekstre dönemi.');
    }

    // Bu alanlar eski ekstre tablosunda zorunlu kaldığı için 0 saklanır;
    // kullanıcıdan istenmez ve PDF'lerde gösterilmez.
    $gun_sayisi = 0;
    $kisi_sayisi = 0;

    // Normal ve mesai verileri yalnızca günlük giriş kayıtlarından alınır.
    $stmt = $pdo->prepare("
        SELECT COALESCE(SUM(yemek_adedi), 0) AS normal_adet,
               COALESCE(SUM(gunluk_toplam_tutar), 0) AS normal_tutar,
               COALESCE(SUM(mesai_yemek_adedi), 0) AS mesai_adet,
               COALESCE(SUM(mesai_toplam_tutar), 0) AS mesai_tutar
        FROM gunluk_yemek_verileri
        WHERE musteri_id = ? AND tarih BETWEEN ? AND ?
    ");
    $stmt->execute([$musteri_id, $baslangic, $bitis]);
    $gunluk_toplamlar = $stmt->fetch();

    $normal_adet = (int)$gunluk_toplamlar['normal_adet'];
    $normal_tutar = (float)$gunluk_toplamlar['normal_tutar'];
    $normal_fiyat = $normal_adet > 0 ? $normal_tutar / $normal_adet : (float)$musteri['anlasilan_yemek_fiyati'];
    $mesai_adet = (int)$gunluk_toplamlar['mesai_adet'];
    $mesai_tutar = (float)$gunluk_toplamlar['mesai_tutar'];
    $mesai_fiyat = $mesai_adet > 0 ? $mesai_tutar / $mesai_adet : (float)$musteri['mesai_yemek_fiyati'];
    // Fazla yemek PDF/ekstre akışında kullanılmaz.
    $fazla_adet = 0;
    $fazla_fiyat = 0.0;
    $onceki_bakiye = (float)str_replace(',', '.', $_POST['onceki_bakiye']);
    $alinan_avans_raw = str_replace(',', '.', $_POST['alinan_avans'] ?? '0');
    $alinan_avans = is_numeric($alinan_avans_raw) ? (float)$alinan_avans_raw : 0.0;

    // PDF formunda elle girilen ödeme, henüz sistemde kayıtlı değilse
    // tahsilat olarak da saklanır. Aynı PDF tekrar üretildiğinde sadece
    // daha önce kaydedilmemiş fark kadar ekleme yapılır.
    $stmt = $pdo->prepare("\n        SELECT COALESCE(SUM(tutar), 0) FROM tahsilatlar\n        WHERE musteri_id = ? AND tarih BETWEEN ? AND ?\n    ");
    $stmt->execute([$musteri_id, $baslangic, $bitis]);
    $kayitli_donem_odemesi = (float)$stmt->fetchColumn();
    if ($alinan_avans > $kayitli_donem_odemesi + 0.004) {
        $yeni_odeme = $alinan_avans - $kayitli_donem_odemesi;
        $stmt = $pdo->prepare("\n            INSERT INTO tahsilatlar (musteri_id, tarih, tutar, aciklama)\n            VALUES (?, ?, ?, ?)\n        ");
        $stmt->execute([$musteri_id, $bitis, $yeni_odeme, 'Ekstre oluşturulurken kaydedilen ödeme']);
    } elseif ($alinan_avans < $kayitli_donem_odemesi) {
        // Sistemdeki tahsilat PDF'ye elle yazılandan fazlaysa gerçek kayıt korunur.
        $alinan_avans = $kayitli_donem_odemesi;
    }

    $fazla_tutar = $fazla_adet * $fazla_fiyat;
    $donem_ara_toplami = $normal_tutar + $mesai_tutar + $fazla_tutar;
    $kdv_orani = !empty($musteri['faturali_mi']) ? 10.0 : 0.0;
    $kdv_tutari = round($donem_ara_toplami * $kdv_orani / 100, 2);
    $donem_toplami = $donem_ara_toplami + $kdv_tutari;
    $kalan_bakiye = $onceki_bakiye + $donem_toplami - $alinan_avans;

    $stmt = $pdo->prepare("
        INSERT INTO ekstreler (
            musteri_id, baslama_tarihi, bitis_tarihi, gun_sayisi, kisi_sayisi,
            normal_yemek_adedi, normal_yemek_fiyati, normal_yemek_tutari,
            mesai_yemek_adedi, mesai_yemek_fiyati, mesai_yemek_tutari,
            fazla_yemek_adedi, fazla_yemek_fiyati, fazla_yemek_tutari,
            onceki_bakiye, donem_ara_toplami, kdv_orani, kdv_tutari,
            donem_toplami, alinan_avans, kalan_bakiye
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ");
    $stmt->execute([
        $musteri_id, $baslangic, $bitis, $gun_sayisi, $kisi_sayisi,
        $normal_adet, $normal_fiyat, $normal_tutar,
        $mesai_adet, $mesai_fiyat, $mesai_tutar,
        $fazla_adet, $fazla_fiyat, $fazla_tutar,
        $onceki_bakiye, $donem_ara_toplami, $kdv_orani, $kdv_tutari,
        $donem_toplami, $alinan_avans, $kalan_bakiye,
    ]);

    $ekstre_id = (int)$pdo->lastInsertId();
    header('Location: ekstre_pdf.php?id=' . $ekstre_id);
    exit;
}

require_once 'includes/header.php';
?>

<div class="flex items-center gap-3 mb-6">
    <a href="musteri_detay.php?id=<?= (int)$musteri_id ?>" class="text-slate-500 hover:text-slate-800 p-2 -ml-2 rounded-lg hover:bg-slate-100 transition">
        <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
    </a>
    <h1 class="text-2xl font-bold text-slate-800">Ekstre / Fatura Oluştur</h1>
</div>

<div class="bg-white rounded-2xl shadow-sm p-5 mb-6">
    <h2 class="text-lg font-bold text-slate-800"><?= h($musteri['sirket_ismi']) ?></h2>
    <p class="text-gray-500 text-sm mt-1">
        Yemek fiyatı: <span class="font-medium text-slate-700"><?= format_para($musteri['anlasilan_yemek_fiyati']) ?></span>
        <?php if ($musteri['mesai_yemek_fiyati'] > 0): ?>
            &nbsp;·&nbsp; Mesai fiyatı: <span class="font-medium text-slate-700"><?= format_para($musteri['mesai_yemek_fiyati']) ?></span>
        <?php endif; ?>
    </p>
    <?php if ($kdv_orani > 0): ?>
        <p class="text-sm text-violet-700 font-medium mt-2">Faturalı müşteri · Ekstreye %10 KDV eklenecek.</p>
    <?php endif; ?>
</div>

<?php if ($hata): ?>
    <div class="bg-red-50 text-red-600 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($hata) ?></div>
<?php endif; ?>

<?php if (!$oneri): ?>
    <!-- ADIM 1: Dönem bilgisi -->
    <form method="POST" class="bg-white rounded-2xl shadow-sm p-5 space-y-4">
        <input type="hidden" name="musteri_id" value="<?= (int)$musteri_id ?>">
        <input type="hidden" name="adim" value="hesapla">

        <h2 class="text-base font-semibold text-slate-700">1. Adım — Dönem Bilgisi</h2>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <label class="block text-sm text-gray-600 mb-1">Başlama Tarihi *</label>
                <input type="date" name="baslangic_tarihi" required value="<?= date('Y-m-01') ?>"
                       class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
            </div>
            <div>
                <label class="block text-sm text-gray-600 mb-1">Bitiş Tarihi *</label>
                <input type="date" name="bitis_tarihi" required value="<?= date('Y-m-d') ?>"
                       class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
            </div>
        </div>

        <button type="submit" class="bg-amber-600 hover:bg-amber-700 active:scale-[0.98] text-white font-medium px-5 py-2.5 rounded-xl transition">
            Devam Et — Değerleri Hesapla
        </button>
    </form>

<?php else: ?>
    <!-- ADIM 2: Hesaplanan öneriler, düzenlenebilir -->
    <form method="POST" class="bg-white rounded-2xl shadow-sm p-5 space-y-6">
        <input type="hidden" name="musteri_id" value="<?= (int)$musteri_id ?>">
        <input type="hidden" name="adim" value="olustur">
        <input type="hidden" name="baslangic_tarihi" value="<?= h($oneri['baslangic']) ?>">
        <input type="hidden" name="bitis_tarihi" value="<?= h($oneri['bitis']) ?>">

        <div>
            <h2 class="text-base font-semibold text-slate-700 mb-1">2. Adım — Değerleri Kontrol Edin</h2>
            <p class="text-xs text-gray-400">
                <?= format_tarih($oneri['baslangic']) ?> – <?= format_tarih($oneri['bitis']) ?> dönemi için günlük girişlerden alınan değerler aşağıdadır. Yemek adetlerini değiştirmek için Günlük Yemek Girişi sayfasını kullanın.
            </p>
        </div>

        <div class="border-t border-slate-100 pt-4">
            <h3 class="text-sm font-semibold text-slate-700 mb-3">Yemek Adedi — Günlük Girişlerden</h3>
            <p class="text-sm text-slate-600">
                <?= $oneri['normal_adet_giris'] ?> adet · <?= format_para($oneri['normal_tutar_giris']) ?>
            </p>
        </div>

        <?php if ($oneri['kdv_orani'] > 0): ?>
            <div class="border-t border-slate-100 pt-4 text-sm text-slate-700">
                <h3 class="font-semibold mb-2">KDV Özeti</h3>
                <p>Ara toplam: <?= format_para($oneri['ara_toplam']) ?> · KDV (%10): <?= format_para($oneri['kdv_tutari']) ?> · KDV dâhil dönem toplamı: <strong><?= format_para($oneri['ara_toplam'] + $oneri['kdv_tutari']) ?></strong></p>
            </div>
        <?php endif; ?>

        <div class="border-t border-slate-100 pt-4">
            <h3 class="text-sm font-semibold text-slate-700 mb-3">Mesai Yemeği — Günlük Girişlerden</h3>
            <p class="text-sm text-slate-600">
                <?= $oneri['mesai_adet_giris'] ?> adet · <?= format_para($oneri['mesai_tutar_giris']) ?>
            </p>
        </div>

        <div class="border-t border-slate-100 pt-4">
            <h3 class="text-sm font-semibold text-slate-700 mb-3">Cari Hesap</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm text-gray-600 mb-1">Önceki Bakiye (₺)</label>
                    <input type="text" name="onceki_bakiye" value="<?= (float)$oneri['onceki_bakiye_oto'] ?>"
                           class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
                    <p class="text-xs text-gray-400 mt-1">Sistemin hesapladığı devir bakiyesi; kağıt kayıtlardan gelen eski bakiyeniz varsa buraya elle yazabilirsiniz.</p>
                </div>
                <div>
                    <label class="block text-sm text-gray-600 mb-1">Alınan Ödeme (₺)</label>
                    <input type="text" name="alinan_avans" value="<?= (float)$oneri['avans_oto'] ?>"
                           class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
                    <p class="text-xs text-gray-400 mt-1">Sistemde olmayan eski ödemeyi buraya yazarsanız, PDF oluşturulurken müşteri tahsilatına otomatik kaydedilir.</p>
                </div>
            </div>
        </div>

        <div class="flex flex-wrap gap-3 pt-2">
            <a href="ekstre_olustur.php?musteri_id=<?= (int)$musteri_id ?>" class="text-slate-500 hover:text-slate-800 px-5 py-2.5 rounded-xl border border-slate-200 transition">
                Geri Dön
            </a>
            <button type="submit" class="bg-emerald-600 hover:bg-emerald-700 active:scale-[0.98] text-white font-medium px-6 py-2.5 rounded-xl transition">
                PDF Oluştur ve İndir
            </button>
        </div>
    </form>
<?php endif; ?>

<?php require_once 'includes/footer.php'; ?>
