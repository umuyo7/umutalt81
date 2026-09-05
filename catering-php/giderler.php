<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$tarih = $_GET['tarih'] ?? date('Y-m-d');
if (!gecerli_tarih_mi($tarih)) {
    $tarih = date('Y-m-d');
}

$kategoriler = ['Personel', 'Yakıt / Nakliye', 'Gıda / Malzeme', 'Paketleme', 'Kira / Fatura', 'Bakım / Onarım', 'Diğer'];
$gider_tablosu_var = (bool)$pdo->query("SHOW TABLES LIKE 'gunluk_giderler'")->fetchColumn();
$kategori_kolonu_var = $gider_tablosu_var && (bool)$pdo->query("SHOW COLUMNS FROM gunluk_giderler LIKE 'kategori'")->fetchColumn();
$mesaj = '';
$hata = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $gider_tablosu_var && $kategori_kolonu_var) {
    $form_tarih = $_POST['tarih'] ?? $tarih;
    if (!gecerli_tarih_mi($form_tarih)) {
        $form_tarih = date('Y-m-d');
    }
    if (isset($_POST['gider_ekle'])) {
        $kategori = $_POST['kategori'] ?? 'Diğer';
        $aciklama = trim($_POST['aciklama'] ?? '');
        $tutar_raw = str_replace(',', '.', trim($_POST['tutar'] ?? '0'));
        if (!in_array($kategori, $kategoriler, true)) {
            $kategori = 'Diğer';
        }
        if ($aciklama === '' || !is_numeric($tutar_raw) || (float)$tutar_raw <= 0) {
            $hata = 'Kategori, açıklama ve 0’dan büyük tutar giriniz.';
        } else {
            $stmt = $pdo->prepare('INSERT INTO gunluk_giderler (tarih, kategori, aciklama, tutar) VALUES (?, ?, ?, ?)');
            $stmt->execute([$form_tarih, $kategori, $aciklama, (float)$tutar_raw]);
            header('Location: giderler.php?tarih=' . urlencode($form_tarih) . '&durum=eklendi');
            exit;
        }
    }
    if (isset($_POST['gider_sil'])) {
        $stmt = $pdo->prepare('DELETE FROM gunluk_giderler WHERE id = ?');
        $stmt->execute([(int)($_POST['gider_id'] ?? 0)]);
        header('Location: giderler.php?tarih=' . urlencode($form_tarih) . '&durum=silindi');
        exit;
    }
}

if (isset($_GET['durum'])) {
    $mesaj = $_GET['durum'] === 'eklendi' ? 'Gider kaydedildi.' : 'Gider silindi.';
}

$giderler = [];
$gunluk_toplam = 0.0;
$kategori_toplamlari = [];
if ($gider_tablosu_var && $kategori_kolonu_var) {
    $stmt = $pdo->prepare('SELECT * FROM gunluk_giderler WHERE tarih = ? ORDER BY id DESC');
    $stmt->execute([$tarih]);
    $giderler = $stmt->fetchAll();
    $gunluk_toplam = array_sum(array_column($giderler, 'tutar'));
    foreach ($giderler as $gider) {
        $kategori_toplamlari[$gider['kategori']] = ($kategori_toplamlari[$gider['kategori']] ?? 0) + (float)$gider['tutar'];
    }
}

require_once 'includes/header.php';
?>

<div class="flex flex-wrap items-center justify-between gap-3 mb-6">
    <h1 class="text-2xl font-bold text-slate-800">Günlük Giderler</h1>
    <form method="GET"><input type="date" name="tarih" value="<?= h($tarih) ?>" onchange="this.form.submit()" class="border border-slate-200 rounded-xl px-3 py-2 focus:ring-2 focus:ring-amber-400 focus:outline-none"></form>
</div>

<?php if ($mesaj): ?><div class="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700"><?= h($mesaj) ?></div><?php endif; ?>
<?php if ($hata): ?><div class="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600"><?= h($hata) ?></div><?php endif; ?>

<?php if (!$gider_tablosu_var || !$kategori_kolonu_var): ?>
    <div class="rounded-2xl bg-amber-50 p-5 text-sm text-amber-800">Bu ekran için phpMyAdmin’den önce <strong>migration_v6.sql</strong>, ardından <strong>migration_v7.sql</strong> dosyalarını birer kez çalıştırın.</div>
<?php else: ?>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <section class="bg-white rounded-2xl shadow-sm p-5 lg:col-span-1">
            <h2 class="font-semibold text-slate-700 mb-4">Gider Ekle</h2>
            <form method="POST" class="space-y-3">
                <input type="hidden" name="tarih" value="<?= h($tarih) ?>">
                <div><label class="block text-sm text-slate-600 mb-1">Kategori</label><select name="kategori" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"><?php foreach ($kategoriler as $kategori): ?><option value="<?= h($kategori) ?>"><?= h($kategori) ?></option><?php endforeach; ?></select></div>
                <div><label class="block text-sm text-slate-600 mb-1">Açıklama</label><input type="text" name="aciklama" required placeholder="Örn: Araç yakıtı" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
                <div><label class="block text-sm text-slate-600 mb-1">Tutar (₺)</label><input type="text" name="tutar" required placeholder="Örn: 350,00" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
                <button type="submit" name="gider_ekle" class="w-full bg-violet-600 hover:bg-violet-700 text-white font-medium px-5 py-2.5 rounded-xl transition">Gideri Kaydet</button>
            </form>
        </section>
        <section class="bg-white rounded-2xl shadow-sm overflow-hidden lg:col-span-2">
            <div class="flex items-center justify-between px-5 pt-5 pb-3"><h2 class="font-semibold text-slate-700">Gider Kayıtları</h2><span class="text-sm font-bold text-violet-700"><?= format_para($gunluk_toplam) ?></span></div>
            <?php foreach ($giderler as $gider): ?>
                <div class="flex items-center gap-3 border-t border-slate-100 px-5 py-3"><span class="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700"><?= h($gider['kategori']) ?></span><p class="min-w-0 flex-1 truncate text-sm text-slate-700"><?= h($gider['aciklama']) ?></p><span class="text-sm font-semibold text-slate-800"><?= format_para($gider['tutar']) ?></span><form method="POST"><input type="hidden" name="tarih" value="<?= h($tarih) ?>"><input type="hidden" name="gider_id" value="<?= (int)$gider['id'] ?>"><button type="submit" name="gider_sil" class="text-xs text-rose-600">Sil</button></form></div>
            <?php endforeach; ?>
            <?php if (!$giderler): ?><p class="border-t border-slate-100 px-5 py-8 text-center text-sm text-slate-400">Bu tarih için gider kaydı yok.</p><?php endif; ?>
        </section>
    </div>
    <?php if ($kategori_toplamlari): ?>
        <section class="mt-5 bg-white rounded-2xl shadow-sm p-5"><h2 class="font-semibold text-slate-700 mb-3">Kategori Toplamları</h2><div class="flex flex-wrap gap-3"><?php foreach ($kategori_toplamlari as $kategori => $toplam): ?><div class="rounded-xl bg-slate-50 px-4 py-3"><p class="text-xs text-slate-500"><?= h($kategori) ?></p><p class="font-bold text-slate-800 mt-1"><?= format_para($toplam) ?></p></div><?php endforeach; ?></div></section>
    <?php endif; ?>
<?php endif; ?>

<?php require_once 'includes/footer.php'; ?>
