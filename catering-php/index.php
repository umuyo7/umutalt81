<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

// Panel her zaman otomatik olarak geçen takvim ayını gösterir.
$secilen_ay = date('Y-m', strtotime('first day of last month'));
$ay_baslangic = $secilen_ay . '-01';
$ay_sonu = date('Y-m-t', strtotime($ay_baslangic));

// Faturalı müşterilerin hizmet tutarına %10 KDV eklenir.
$stmt = $pdo->prepare("
    SELECT COALESCE(SUM((g.gunluk_toplam_tutar + g.mesai_toplam_tutar) *
        (1 + CASE WHEN m.faturali_mi = 1 THEN 0.10 ELSE 0 END)), 0)
    FROM gunluk_yemek_verileri g
    JOIN musteriler m ON m.id = g.musteri_id
    WHERE g.tarih BETWEEN ? AND ?
");
$stmt->execute([$ay_baslangic, $ay_sonu]);
$aylik_musteri_ciro = (float)$stmt->fetchColumn();

$stmt = $pdo->prepare("SELECT COALESCE(SUM(toplam_tutar), 0) FROM taziye_yemekleri WHERE tarih BETWEEN ? AND ?");
$stmt->execute([$ay_baslangic, $ay_sonu]);
$aylik_taziye_ciro = (float)$stmt->fetchColumn();
$aylik_ciro = $aylik_musteri_ciro + $aylik_taziye_ciro;

$stmt = $pdo->prepare("SELECT COALESCE(SUM(tutar), 0) FROM tahsilatlar WHERE tarih BETWEEN ? AND ?");
$stmt->execute([$ay_baslangic, $ay_sonu]);
$aylik_tahsilat = (float)$stmt->fetchColumn();

// Her müşterinin ay sonundaki borcu ayrı hesaplanır; bir müşterinin avansı
// diğer müşterinin borcunu düşürmez. Taziye siparişleri cari borca eklenmez.
$stmt = $pdo->prepare("
    SELECT COALESCE(SUM(GREATEST(0, hizmet - tahsilat)), 0) FROM (
        SELECT m.id,
            COALESCE(m.devreden_borc, 0) + COALESCE((SELECT SUM((g.gunluk_toplam_tutar + g.mesai_toplam_tutar) *
                (1 + CASE WHEN m.faturali_mi = 1 THEN 0.10 ELSE 0 END))
                FROM gunluk_yemek_verileri g WHERE g.musteri_id = m.id AND g.tarih <= ?), 0) AS hizmet,
            COALESCE((SELECT SUM(t.tutar) FROM tahsilatlar t WHERE t.musteri_id = m.id AND t.tarih <= ?), 0) AS tahsilat
        FROM musteriler m
    ) AS musteri_bakiyeleri
");
$stmt->execute([$ay_sonu, $ay_sonu]);
$ay_sonu_borc = (float)$stmt->fetchColumn();

// Toplam müşteri sayısı
$musteri_sayisi = (int)$pdo->query(
    "SELECT COUNT(*) AS c FROM musteriler WHERE aktif_mi = 1"
)->fetch()['c'];

// 5) Bugün normal yemek verilen toplam kişi sayısı
$bugun_yemek_verilen_kisi = (int)$pdo->query(
    "SELECT COALESCE(SUM(yemek_adedi), 0) AS c FROM gunluk_yemek_verileri WHERE tarih = CURDATE()"
)->fetch()['c'];

// Bugünün giderleri (gider tablosu henüz kurulmadıysa 0 gösterilir).
$gider_tablosu_var = (bool)$pdo->query("SHOW TABLES LIKE 'gunluk_giderler'")->fetchColumn();
$bugun_gideri = 0.0;
if ($gider_tablosu_var) {
    $stmt = $pdo->prepare("SELECT COALESCE(SUM(tutar), 0) FROM gunluk_giderler WHERE tarih = ?");
    $stmt->execute([date('Y-m-d')]);
    $bugun_gideri = (float)$stmt->fetchColumn();
}

// Son 12 ay için KDV dâhil ciro grafiği. Kayıt olmayan aylarda 0 gösterilir.
$grafik_baslangic = date('Y-m-01', strtotime('-11 months'));
$stmt = $pdo->prepare("
    SELECT ay, SUM(tutar) AS toplam FROM (
        SELECT DATE_FORMAT(g.tarih, '%Y-%m') AS ay,
               SUM((g.gunluk_toplam_tutar + g.mesai_toplam_tutar) *
                   (1 + CASE WHEN m.faturali_mi = 1 THEN 0.10 ELSE 0 END)) AS tutar
        FROM gunluk_yemek_verileri g JOIN musteriler m ON m.id = g.musteri_id
        WHERE g.tarih >= ? GROUP BY ay
        UNION ALL
        SELECT DATE_FORMAT(tarih, '%Y-%m') AS ay, SUM(toplam_tutar) AS tutar
        FROM taziye_yemekleri WHERE tarih >= ? GROUP BY ay
    ) AS aylik_kayitlar
    GROUP BY ay
");
$stmt->execute([$grafik_baslangic, $grafik_baslangic]);
$grafik_kayitlari = [];
foreach ($stmt->fetchAll() as $kayit) {
    $grafik_kayitlari[$kayit['ay']] = (float)$kayit['toplam'];
}
$aylar = [];
$tutarlar = [];
$grafik_ayi = new DateTime($grafik_baslangic);
for ($i = 0; $i < 12; $i++) {
    $anahtar = $grafik_ayi->format('Y-m');
    $aylar[] = $grafik_ayi->format('m.Y');
    $tutarlar[] = $grafik_kayitlari[$anahtar] ?? 0;
    $grafik_ayi->modify('+1 month');
}

require_once 'includes/header.php';
?>

<h1 class="text-2xl font-bold text-slate-800 mb-6">Sistem Özeti</h1>

<p class="mb-6 text-sm text-slate-500">Paneldeki ciro, tahsilat ve borç bilgileri otomatik olarak <strong>geçen ay</strong> için gösterilir.</p>

<div class="grid grid-cols-2 lg:grid-cols-6 gap-4 mb-8">

    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-amber-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Geçen Ay Cirosu</p>
        <p class="text-xl sm:text-2xl font-bold text-slate-800 mt-2"><?= format_para($aylik_ciro) ?></p>
    </div>

    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-emerald-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Geçen Ay Tahsilat</p>
        <p class="text-xl sm:text-2xl font-bold text-emerald-600 mt-2"><?= format_para($aylik_tahsilat) ?></p>
    </div>

    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-rose-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Geçen Ay Sonu Borç</p>
        <p class="text-xl sm:text-2xl font-bold text-rose-600 mt-2"><?= format_para($ay_sonu_borc) ?></p>
    </div>

    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-indigo-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Aktif Müşteri</p>
        <p class="text-xl sm:text-2xl font-bold text-slate-800 mt-2"><?= $musteri_sayisi ?></p>
    </div>

    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-sky-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Bugün Yemek Verilen Kişi</p>
        <p class="text-xl sm:text-2xl font-bold text-sky-700 mt-2"><?= $bugun_yemek_verilen_kisi ?></p>
    </div>

    <a href="giderler.php" class="bg-white rounded-2xl shadow-sm border-b-4 border-violet-500 p-5 hover:bg-violet-50 transition">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Bugünün Gideri</p>
        <p class="text-xl sm:text-2xl font-bold text-violet-700 mt-2"><?= format_para($bugun_gideri) ?></p>
    </a>

</div>

<div class="bg-white rounded-2xl shadow-sm p-5">
    <h2 class="text-base font-semibold text-slate-700 mb-1">Son 12 Ay Ciro Grafiği</h2>
    <p class="text-xs text-slate-400 mb-4">Faturalı müşterilerde %10 KDV dâhil, taziye yemekleri dâhil.</p>
    <canvas id="ciroChart" height="180"></canvas>
</div>

<script>
const ctx = document.getElementById('ciroChart');
new Chart(ctx, {
    type: 'line',
    data: {
        labels: <?= json_encode($aylar, JSON_UNESCAPED_UNICODE) ?>,
        datasets: [{
            label: 'Aylık Ciro (₺)',
            data: <?= json_encode($tutarlar) ?>,
            borderColor: 'rgb(217, 119, 6)',
            backgroundColor: 'rgba(217, 119, 6, 0.12)',
            tension: 0.35,
            fill: true,
            pointRadius: 4,
            pointBackgroundColor: 'rgb(217, 119, 6)'
        }]
    },
    options: {
        responsive: true,
        plugins: { legend: { display: true } },
        scales: { y: { beginAtZero: true } }
    }
});
</script>

<?php require_once 'includes/footer.php'; ?>
