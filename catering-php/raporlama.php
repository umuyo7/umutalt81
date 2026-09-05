<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$tarih = $_GET['tarih'] ?? date('Y-m-d');
if (!gecerli_tarih_mi($tarih)) {
    $tarih = date('Y-m-d');
}

$gider_tablosu_var = (bool)$pdo->query("SHOW TABLES LIKE 'gunluk_giderler'")->fetchColumn();
$mesaj = '';
$hata = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $gider_tablosu_var) {
    $form_tarih = $_POST['tarih'] ?? $tarih;
    if (!gecerli_tarih_mi($form_tarih)) {
        $form_tarih = date('Y-m-d');
    }

    if (isset($_POST['gider_ekle'])) {
        $aciklama = trim($_POST['aciklama'] ?? '');
        $tutar_raw = str_replace(',', '.', trim($_POST['tutar'] ?? '0'));
        if ($aciklama === '' || !is_numeric($tutar_raw) || (float)$tutar_raw <= 0) {
            $hata = 'Gider açıklaması ve 0’dan büyük tutar giriniz.';
        } else {
            $stmt = $pdo->prepare('INSERT INTO gunluk_giderler (tarih, aciklama, tutar) VALUES (?, ?, ?)');
            $stmt->execute([$form_tarih, $aciklama, (float)$tutar_raw]);
            header('Location: raporlama.php?tarih=' . urlencode($form_tarih) . '&gider=eklendi');
            exit;
        }
    }
    if (isset($_POST['gider_sil'])) {
        $stmt = $pdo->prepare('DELETE FROM gunluk_giderler WHERE id = ?');
        $stmt->execute([(int)($_POST['gider_id'] ?? 0)]);
        header('Location: raporlama.php?tarih=' . urlencode($form_tarih) . '&gider=silindi');
        exit;
    }
}

if (isset($_GET['gider'])) {
    $mesaj = $_GET['gider'] === 'eklendi' ? 'Günlük gider kaydedildi.' : 'Gider kaydı silindi.';
}

$ciro_hesapla = function (string $baslangic, string $bitis) use ($pdo): float {
    $stmt = $pdo->prepare("
        SELECT COALESCE(SUM((g.gunluk_toplam_tutar + g.mesai_toplam_tutar) *
            (1 + CASE WHEN m.faturali_mi = 1 THEN 0.10 ELSE 0 END)), 0)
        FROM gunluk_yemek_verileri g JOIN musteriler m ON m.id = g.musteri_id
        WHERE g.tarih BETWEEN ? AND ?
    ");
    $stmt->execute([$baslangic, $bitis]);
    $musteri_ciro = (float)$stmt->fetchColumn();
    $stmt = $pdo->prepare('SELECT COALESCE(SUM(toplam_tutar), 0) FROM taziye_yemekleri WHERE tarih BETWEEN ? AND ?');
    $stmt->execute([$baslangic, $bitis]);
    return $musteri_ciro + (float)$stmt->fetchColumn();
};

$secilen_ay_baslangic = date('Y-m-01', strtotime($tarih));
$secilen_ay_sonu = date('Y-m-t', strtotime($tarih));
$gunluk_ciro = $ciro_hesapla($tarih, $tarih);
$aylik_ciro = $ciro_hesapla($secilen_ay_baslangic, $secilen_ay_sonu);

// Her müşteri ayrı değerlendirildiği için bir müşterinin avansı diğerinin borcunu kapatmaz.
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
$stmt->execute([$tarih, $tarih]);
$toplam_alacak = (float)$stmt->fetchColumn();

$stmt = $pdo->prepare('SELECT COALESCE(SUM(yemek_adedi), 0) AS normal_adet, COALESCE(SUM(mesai_yemek_adedi), 0) AS mesai_adet FROM gunluk_yemek_verileri WHERE tarih = ?');
$stmt->execute([$tarih]);
$gunluk_adetler = $stmt->fetch();
$gunluk_normal_adet = (int)$gunluk_adetler['normal_adet'];
$gunluk_mesai_adet = (int)$gunluk_adetler['mesai_adet'];
$gunluk_toplam_adet = $gunluk_normal_adet + $gunluk_mesai_adet;

$gunluk_gider = 0.0;
$aylik_gider = 0.0;
$giderler = [];
if ($gider_tablosu_var) {
    $stmt = $pdo->prepare('SELECT * FROM gunluk_giderler WHERE tarih = ? ORDER BY id DESC');
    $stmt->execute([$tarih]);
    $giderler = $stmt->fetchAll();
    $gunluk_gider = array_sum(array_column($giderler, 'tutar'));

    $stmt = $pdo->prepare('SELECT COALESCE(SUM(tutar), 0) FROM gunluk_giderler WHERE tarih BETWEEN ? AND ?');
    $stmt->execute([$secilen_ay_baslangic, $secilen_ay_sonu]);
    $aylik_gider = (float)$stmt->fetchColumn();
}

$gunluk_net = $gunluk_ciro - $gunluk_gider;
$aylik_net = $aylik_ciro - $aylik_gider;

require_once 'includes/header.php';
?>

<div class="flex flex-wrap items-center justify-between gap-3 mb-6">
    <h1 class="text-2xl font-bold text-slate-800">Raporlama</h1>
    <form method="GET" class="flex items-center gap-2">
        <label for="tarih" class="text-sm text-slate-500">Gün</label>
        <input id="tarih" type="date" name="tarih" value="<?= h($tarih) ?>" onchange="this.form.submit()" class="border border-slate-200 rounded-xl px-3 py-2 focus:ring-2 focus:ring-amber-400 focus:outline-none">
    </form>
</div>

<?php if ($mesaj): ?><div class="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700"><?= h($mesaj) ?></div><?php endif; ?>
<?php if ($hata): ?><div class="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600"><?= h($hata) ?></div><?php endif; ?>

<section class="mb-7">
    <div class="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div><h2 class="text-lg font-bold text-slate-800">Seçilen Gün</h2><p class="text-sm text-slate-400"><?= h(format_tarih($tarih)) ?></p></div>
        <p class="text-xs text-slate-400">Ciro KDV dâhil hizmet toplamıdır; net sonuçtan günlük gider düşülür.</p>
    </div>
    <div class="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div class="bg-white rounded-2xl shadow-sm border-b-4 border-emerald-500 p-5"><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Günlük Ciro</p><p class="mt-2 text-xl font-bold text-emerald-700"><?= format_para($gunluk_ciro) ?></p></div>
        <div class="bg-white rounded-2xl shadow-sm border-b-4 border-sky-500 p-5"><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Normal Yemek</p><p class="mt-2 text-xl font-bold text-sky-700"><?= number_format($gunluk_normal_adet, 0, ',', '.') ?></p></div>
        <div class="bg-white rounded-2xl shadow-sm border-b-4 border-cyan-500 p-5"><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Mesai Yemeği</p><p class="mt-2 text-xl font-bold text-cyan-700"><?= number_format($gunluk_mesai_adet, 0, ',', '.') ?></p><p class="mt-1 text-xs text-slate-400">Toplam: <?= number_format($gunluk_toplam_adet, 0, ',', '.') ?></p></div>
        <div class="bg-white rounded-2xl shadow-sm border-b-4 border-violet-500 p-5"><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Günlük Gider</p><p class="mt-2 text-xl font-bold text-violet-700"><?= format_para($gunluk_gider) ?></p></div>
        <div class="bg-white rounded-2xl shadow-sm border-b-4 <?= $gunluk_net < 0 ? 'border-rose-500' : 'border-amber-500' ?> p-5"><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Günlük Net</p><p class="mt-2 text-xl font-bold <?= $gunluk_net < 0 ? 'text-rose-600' : 'text-amber-700' ?>"><?= format_para($gunluk_net) ?></p></div>
    </div>
</section>

<section class="mb-7">
    <div class="mb-3"><h2 class="text-lg font-bold text-slate-800">Seçilen Ay</h2><p class="text-sm text-slate-400"><?= h(date('m/Y', strtotime($tarih))) ?></p></div>
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div class="bg-white rounded-2xl shadow-sm border-b-4 border-emerald-500 p-5"><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Aylık Ciro</p><p class="mt-2 text-xl font-bold text-emerald-700"><?= format_para($aylik_ciro) ?></p></div>
        <div class="bg-white rounded-2xl shadow-sm border-b-4 border-violet-500 p-5"><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Aylık Gider</p><p class="mt-2 text-xl font-bold text-violet-700"><?= format_para($aylik_gider) ?></p></div>
        <div class="bg-white rounded-2xl shadow-sm border-b-4 <?= $aylik_net < 0 ? 'border-rose-500' : 'border-amber-500' ?> p-5"><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Aylık Net</p><p class="mt-2 text-xl font-bold <?= $aylik_net < 0 ? 'text-rose-600' : 'text-amber-700' ?>"><?= format_para($aylik_net) ?></p></div>
    </div>
</section>

<section class="mb-7">
    <div class="rounded-2xl bg-white shadow-sm border-l-4 border-rose-500 p-5">
        <div class="flex flex-wrap items-center justify-between gap-2"><div><p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Genel Durum · Seçilen Tarihe Kadar</p><p class="mt-2 text-2xl font-bold text-rose-600"><?= format_para($toplam_alacak) ?></p></div><p class="max-w-md text-xs text-slate-400">Müşteri bazında devreden borç ve hizmetlerden tahsilatlar düşülerek hesaplanan toplam alacak.</p></div>
    </div>
</section>
</div>

<?php if (!$gider_tablosu_var): ?>
    <div class="rounded-2xl bg-amber-50 p-5 text-sm text-amber-800">Günlük gider alanını kullanmak için önce <strong>migration_v6.sql</strong> dosyasını phpMyAdmin’den bir kez çalıştırın.</div>
<?php else: ?>
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <section class="bg-white rounded-2xl shadow-sm p-5">
            <h2 class="font-semibold text-slate-700 mb-4">Günlük Gider Ekle</h2>
            <form method="POST" class="space-y-3">
                <input type="hidden" name="tarih" value="<?= h($tarih) ?>">
                <div><label class="block text-sm text-slate-600 mb-1">Açıklama</label><input type="text" name="aciklama" required placeholder="Örn: Yakıt, market, paketleme" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
                <div><label class="block text-sm text-slate-600 mb-1">Tutar (₺)</label><input type="text" name="tutar" required placeholder="Örn: 250,00" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
                <button type="submit" name="gider_ekle" class="bg-violet-600 hover:bg-violet-700 text-white font-medium px-5 py-2.5 rounded-xl transition">Gideri Kaydet</button>
            </form>
        </section>
        <section class="bg-white rounded-2xl shadow-sm overflow-hidden">
            <h2 class="px-5 pt-5 pb-3 font-semibold text-slate-700">Seçilen Günün Giderleri</h2>
            <?php foreach ($giderler as $gider): ?>
                <div class="flex items-center gap-3 border-t border-slate-100 px-5 py-3"><div class="min-w-0 flex-1"><p class="truncate text-sm font-medium text-slate-700"><?= h($gider['aciklama']) ?></p></div><span class="text-sm font-semibold text-violet-700"><?= format_para($gider['tutar']) ?></span><form method="POST"><input type="hidden" name="tarih" value="<?= h($tarih) ?>"><input type="hidden" name="gider_id" value="<?= (int)$gider['id'] ?>"><button type="submit" name="gider_sil" class="text-xs text-rose-600">Sil</button></form></div>
            <?php endforeach; ?>
            <?php if (!$giderler): ?><p class="border-t border-slate-100 px-5 py-7 text-center text-sm text-slate-400">Bu gün için gider girilmedi.</p><?php endif; ?>
        </section>
    </div>
<?php endif; ?>

<?php require_once 'includes/footer.php'; ?>
