<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$maasTablolariVar = (bool)$pdo->query("SHOW TABLES LIKE 'calisanlar'")->fetchColumn()
    && (bool)$pdo->query("SHOW TABLES LIKE 'maas_odemeleri'")->fetchColumn();

if (!$maasTablolariVar) {
    require_once 'includes/header.php';
    ?>
    <h1 class="text-2xl font-bold text-slate-800 mb-6">Çalışanlar ve Maaş Giderleri</h1>
    <div class="bg-amber-50 text-amber-800 p-5 rounded-2xl text-sm">
        Maaş takibini kullanmadan önce <strong>migration_v3.sql</strong> dosyasını phpMyAdmin’de bir kez çalıştırın.
    </div>
    <?php
    require_once 'includes/footer.php';
    exit;
}

$hata = '';
$basari = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['calisan_ekle'])) {
    $ad_soyad = trim($_POST['ad_soyad'] ?? '');
    $gorev = trim($_POST['gorev'] ?? '');
    $telefon = trim($_POST['telefon'] ?? '');
    $maasRaw = str_replace(',', '.', trim($_POST['aylik_maas'] ?? '0'));
    $ise_giris_tarihi = $_POST['ise_giris_tarihi'] ?? '';

    if ($ad_soyad === '') {
        $hata = 'Çalışan adı soyadı zorunludur.';
    } elseif (!is_numeric($maasRaw) || (float)$maasRaw < 0) {
        $hata = 'Geçerli bir aylık maaş giriniz.';
    } elseif ($ise_giris_tarihi !== '' && !preg_match('/^\d{4}-\d{2}-\d{2}$/', $ise_giris_tarihi)) {
        $hata = 'Geçerli bir işe giriş tarihi giriniz.';
    } else {
        $stmt = $pdo->prepare('INSERT INTO calisanlar (ad_soyad, gorev, telefon, aylik_maas, ise_giris_tarihi) VALUES (?, ?, ?, ?, ?)');
        $stmt->execute([$ad_soyad, $gorev ?: null, $telefon ?: null, (float)$maasRaw, $ise_giris_tarihi ?: null]);
        $basari = 'Çalışan başarıyla eklendi.';
    }
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['maas_ode'])) {
    $calisan_id = (int)($_POST['calisan_id'] ?? 0);
    $donem = $_POST['donem'] ?? '';
    $tarih = $_POST['tarih'] ?? date('Y-m-d');
    $tutarRaw = str_replace(',', '.', trim($_POST['tutar'] ?? '0'));
    $aciklama = trim($_POST['aciklama'] ?? '');

    if ($calisan_id <= 0 || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $donem) || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $tarih)) {
        $hata = 'Maaş ödemesi için çalışan ve geçerli tarihler seçiniz.';
    } elseif (!is_numeric($tutarRaw) || (float)$tutarRaw <= 0) {
        $hata = 'Ödeme tutarı sıfırdan büyük olmalıdır.';
    } else {
        $stmt = $pdo->prepare('SELECT id FROM calisanlar WHERE id = ? AND aktif = 1');
        $stmt->execute([$calisan_id]);
        if (!$stmt->fetch()) {
            $hata = 'Aktif çalışan bulunamadı.';
        } else {
            $stmt = $pdo->prepare('INSERT INTO maas_odemeleri (calisan_id, donem, tarih, tutar, aciklama) VALUES (?, ?, ?, ?, ?)');
            $stmt->execute([$calisan_id, $donem, $tarih, (float)$tutarRaw, $aciklama ?: null]);
            $basari = 'Maaş ödemesi kaydedildi.';
        }
    }
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['durum_degistir'])) {
    $calisan_id = (int)($_POST['calisan_id'] ?? 0);
    $aktif = (int)($_POST['aktif'] ?? 0) ? 1 : 0;
    $stmt = $pdo->prepare('UPDATE calisanlar SET aktif = ? WHERE id = ?');
    $stmt->execute([$aktif, $calisan_id]);
    $basari = $aktif ? 'Çalışan tekrar aktif edildi.' : 'Çalışan pasife alındı.';
}

$buAy = date('Y-m-01');
$stmt = $pdo->prepare("SELECT COALESCE(SUM(tutar), 0) FROM maas_odemeleri WHERE donem = ?");
$stmt->execute([$buAy]);
$buAyOdenen = (float)$stmt->fetchColumn();
$aktifMaasToplami = (float)$pdo->query('SELECT COALESCE(SUM(aylik_maas), 0) FROM calisanlar WHERE aktif = 1')->fetchColumn();

$stmt = $pdo->prepare("
    SELECT c.*, COALESCE(SUM(CASE WHEN m.donem = ? THEN m.tutar ELSE 0 END), 0) AS bu_ay_odenen
    FROM calisanlar c
    LEFT JOIN maas_odemeleri m ON m.calisan_id = c.id
    GROUP BY c.id
    ORDER BY c.aktif DESC, c.ad_soyad ASC
");
$stmt->execute([$buAy]);
$calisanlar = $stmt->fetchAll();

$odemeler = $pdo->query("
    SELECT m.*, c.ad_soyad
    FROM maas_odemeleri m
    JOIN calisanlar c ON c.id = m.calisan_id
    ORDER BY m.tarih DESC, m.id DESC
    LIMIT 50
")->fetchAll();

require_once 'includes/header.php';
?>

<h1 class="text-2xl font-bold text-slate-800 mb-6">Çalışanlar ve Maaş Giderleri</h1>

<?php if ($hata): ?>
    <div class="bg-red-50 text-red-600 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($hata) ?></div>
<?php endif; ?>
<?php if ($basari): ?>
    <div class="bg-emerald-50 text-emerald-700 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($basari) ?></div>
<?php endif; ?>

<div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-amber-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Aktif Çalışan Aylık Maaş Toplamı</p>
        <p class="text-xl font-bold text-slate-800 mt-2"><?= format_para($aktifMaasToplami) ?></p>
    </div>
    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-rose-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide"><?= date('m.Y') ?> İçin Kaydedilen Maaş Gideri</p>
        <p class="text-xl font-bold text-rose-600 mt-2"><?= format_para($buAyOdenen) ?></p>
    </div>
</div>

<div class="bg-white rounded-2xl shadow-sm p-5 mb-6">
    <h2 class="text-base font-semibold text-slate-700 mb-4">Yeni Çalışan Ekle</h2>
    <form method="POST" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <div><label class="block text-sm text-gray-600 mb-1">Ad Soyad *</label><input type="text" name="ad_soyad" required class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Görev</label><input type="text" name="gorev" placeholder="Aşçı, şoför..." class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Telefon</label><input type="text" name="telefon" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Aylık Maaş (₺) *</label><input type="text" name="aylik_maas" required placeholder="0.00" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">İşe Giriş Tarihi</label><input type="date" name="ise_giris_tarihi" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div class="lg:col-span-5"><button type="submit" name="calisan_ekle" class="bg-amber-600 hover:bg-amber-700 text-white font-medium px-5 py-2.5 rounded-xl transition">Çalışan Ekle</button></div>
    </form>
</div>

<div class="bg-white rounded-2xl shadow-sm overflow-hidden mb-6">
    <h2 class="px-5 pt-5 pb-2 text-base font-semibold text-slate-700">Çalışan Listesi ve Maaş Ödemesi</h2>
    <div class="overflow-x-auto">
        <table class="w-full text-sm text-left">
            <thead class="text-slate-400 uppercase text-xs"><tr><th class="px-5 py-3">Çalışan</th><th class="px-5 py-3">Görev</th><th class="px-5 py-3">Aylık Maaş</th><th class="px-5 py-3">Bu Ay Ödenen</th><th class="px-5 py-3">Durum</th><th class="px-5 py-3"></th></tr></thead>
            <tbody class="divide-y divide-slate-100">
            <?php foreach ($calisanlar as $c): ?>
                <tr class="hover:bg-amber-50/50">
                    <td class="px-5 py-3 font-medium"><?= h($c['ad_soyad']) ?><span class="block text-xs text-slate-400 font-normal"><?= h($c['telefon']) ?></span></td>
                    <td class="px-5 py-3 text-slate-600"><?= h($c['gorev']) ?: '—' ?></td>
                    <td class="px-5 py-3"><?= format_para($c['aylik_maas']) ?></td>
                    <td class="px-5 py-3 text-emerald-600"><?= format_para($c['bu_ay_odenen']) ?></td>
                    <td class="px-5 py-3"><?= $c['aktif'] ? 'Aktif' : 'Pasif' ?></td>
                    <td class="px-5 py-3 text-right whitespace-nowrap">
                        <?php if ($c['aktif']): ?>
                            <button type="button" onclick="document.getElementById('odeme-<?= (int)$c['id'] ?>').classList.toggle('hidden')" class="text-emerald-700 hover:underline text-xs font-medium">Maaş Öde</button>
                        <?php endif; ?>
                        <form method="POST" class="inline ml-2"><input type="hidden" name="calisan_id" value="<?= (int)$c['id'] ?>"><input type="hidden" name="aktif" value="<?= $c['aktif'] ? 0 : 1 ?>"><button type="submit" name="durum_degistir" class="text-slate-500 hover:underline text-xs"><?= $c['aktif'] ? 'Pasife Al' : 'Aktif Et' ?></button></form>
                    </td>
                </tr>
                <?php if ($c['aktif']): ?>
                <tr id="odeme-<?= (int)$c['id'] ?>" class="hidden bg-slate-50"><td colspan="6" class="px-5 py-4">
                    <form method="POST" class="flex flex-wrap items-end gap-3">
                        <input type="hidden" name="calisan_id" value="<?= (int)$c['id'] ?>">
                        <div><label class="block text-xs text-gray-500 mb-1">Maaş Dönemi</label><input type="month" name="donem_ay" value="<?= date('Y-m') ?>" oninput="this.form.donem.value=this.value+'-01'" class="border border-slate-200 rounded-lg px-2 py-2"></div>
                        <input type="hidden" name="donem" value="<?= $buAy ?>">
                        <div><label class="block text-xs text-gray-500 mb-1">Ödeme Tarihi</label><input type="date" name="tarih" value="<?= date('Y-m-d') ?>" class="border border-slate-200 rounded-lg px-2 py-2"></div>
                        <div><label class="block text-xs text-gray-500 mb-1">Tutar (₺)</label><input type="text" name="tutar" value="<?= h(number_format((float)$c['aylik_maas'], 2, '.', '')) ?>" class="border border-slate-200 rounded-lg px-2 py-2 w-32"></div>
                        <div><label class="block text-xs text-gray-500 mb-1">Açıklama</label><input type="text" name="aciklama" placeholder="Maaş, avans..." class="border border-slate-200 rounded-lg px-2 py-2"></div>
                        <button type="submit" name="maas_ode" class="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg">Ödemeyi Kaydet</button>
                    </form>
                </td></tr>
                <?php endif; ?>
            <?php endforeach; ?>
            <?php if (!$calisanlar): ?><tr><td colspan="6" class="px-5 py-6 text-center text-gray-400">Henüz çalışan eklenmedi.</td></tr><?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<div class="bg-white rounded-2xl shadow-sm overflow-hidden">
    <h2 class="px-5 pt-5 pb-2 text-base font-semibold text-slate-700">Maaş Ödeme Geçmişi</h2>
    <div class="overflow-x-auto"><table class="w-full text-sm text-left"><thead class="text-slate-400 uppercase text-xs"><tr><th class="px-5 py-3">Tarih</th><th class="px-5 py-3">Dönem</th><th class="px-5 py-3">Çalışan</th><th class="px-5 py-3">Açıklama</th><th class="px-5 py-3">Tutar</th></tr></thead><tbody class="divide-y divide-slate-100">
    <?php foreach ($odemeler as $o): ?><tr><td class="px-5 py-2"><?= format_tarih($o['tarih']) ?></td><td class="px-5 py-2"><?= date('m.Y', strtotime($o['donem'])) ?></td><td class="px-5 py-2"><?= h($o['ad_soyad']) ?></td><td class="px-5 py-2"><?= h($o['aciklama']) ?></td><td class="px-5 py-2 text-rose-600"><?= format_para($o['tutar']) ?></td></tr><?php endforeach; ?>
    <?php if (!$odemeler): ?><tr><td colspan="5" class="px-5 py-6 text-center text-gray-400">Henüz maaş ödemesi kaydedilmedi.</td></tr><?php endif; ?>
    </tbody></table></div>
</div>

<?php require_once 'includes/footer.php'; ?>
