<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$hata = '';
$basari = '';

// --- Faturalı müşteri etiketi değiştirme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['fatura_durum_degistir'])) {
    $etiketlenecek_id = (int)($_POST['musteri_id'] ?? 0);
    $faturali_mi = (int)($_POST['faturali_mi'] ?? 0) ? 1 : 0;
    $stmt = $pdo->prepare('UPDATE musteriler SET faturali_mi = ? WHERE id = ?');
    $stmt->execute([$faturali_mi, $etiketlenecek_id]);
    $basari = $faturali_mi ? 'Müşteri faturalı olarak etiketlendi.' : 'Faturalı müşteri etiketi kaldırıldı.';
}

// --- Müşteri silme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['sil'])) {
    $silinecek_id = (int)($_POST['musteri_id'] ?? 0);
    if ($silinecek_id <= 0) {
        $hata = 'Silinecek müşteri bulunamadı.';
    } else {
        $stmt = $pdo->prepare('DELETE FROM musteriler WHERE id = ?');
        $stmt->execute([$silinecek_id]);
        $basari = $stmt->rowCount() ? 'Müşteri ve ona bağlı kayıtlar silindi.' : 'Müşteri bulunamadı.';
    }
}

// --- Yeni müşteri ekleme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['ekle'])) {
    $sirket_ismi = trim($_POST['sirket_ismi'] ?? '');
    $sahis_adi   = trim($_POST['sahis_adi'] ?? '');
    $telefon     = trim($_POST['telefon'] ?? '');
    $eposta      = trim($_POST['eposta'] ?? '');
    $adres       = trim($_POST['adres'] ?? '');
    $faturali_mi = isset($_POST['faturali_mi']) ? 1 : 0;
    $aktif_mi = isset($_POST['aktif_mi']) ? 1 : 0;
    $varsayilan_kisi_sayisi = (int)($_POST['varsayilan_kisi_sayisi'] ?? 0);
    $devreden_borc_raw = str_replace(',', '.', trim($_POST['devreden_borc'] ?? '0'));
    $fiyat_raw   = str_replace(',', '.', trim($_POST['anlasilan_yemek_fiyati'] ?? '0'));
    $mesai_fiyat_raw = str_replace(',', '.', trim($_POST['mesai_yemek_fiyati'] ?? '0'));

    if ($sirket_ismi === '') {
        $hata = 'Şirket ismi zorunludur.';
    } elseif (!is_numeric($fiyat_raw) || (float)$fiyat_raw < 0) {
        $hata = 'Lütfen geçerli bir yemek fiyatı giriniz.';
    } elseif ($mesai_fiyat_raw !== '' && !is_numeric($mesai_fiyat_raw)) {
        $hata = 'Lütfen geçerli bir mesai yemeği fiyatı giriniz.';
    } elseif ($varsayilan_kisi_sayisi < 0) {
        $hata = 'Varsayılan kişi sayısı 0 veya daha büyük olmalıdır.';
    } elseif (!is_numeric($devreden_borc_raw) || (float)$devreden_borc_raw < 0) {
        $hata = 'Devreden borcu geçerli bir tutar olarak giriniz.';
    } else {
        $stmt = $pdo->prepare(
            "INSERT INTO musteriler (sirket_ismi, sahis_adi, telefon, eposta, adres, anlasilan_yemek_fiyati, mesai_yemek_fiyati, varsayilan_kisi_sayisi, faturali_mi, devreden_borc, aktif_mi)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        );
        $stmt->execute([$sirket_ismi, $sahis_adi, $telefon, $eposta, $adres, (float)$fiyat_raw, (float)($mesai_fiyat_raw ?: 0), $varsayilan_kisi_sayisi, $faturali_mi, (float)$devreden_borc_raw, $aktif_mi]);
        $basari = 'Müşteri başarıyla eklendi.';
    }
}

$siralama = $_GET['siralama'] ?? 'yeni';
$siralama_sql = [
    'yeni' => 'm.kayit_tarihi DESC',
    'eski' => 'm.kayit_tarihi ASC',
    'ad_artan' => 'm.sirket_ismi ASC',
    'ad_azalan' => 'm.sirket_ismi DESC',
    'borc_coktan_aza' => 'acik_borc DESC, m.sirket_ismi ASC',
    'odeme_coktan_aza' => 'toplam_odeme DESC, m.sirket_ismi ASC',
];
if (!isset($siralama_sql[$siralama])) {
    $siralama = 'yeni';
}

// Her müşterinin hizmeti, ödemesi ve açık borcu liste üzerinde görülür.
// Faturalı müşterilerin hizmet toplamına %10 KDV dâhildir.
$musteriler = $pdo->query("
    SELECT m.*,
        m.devreden_borc + COALESCE((
            SELECT SUM((g.gunluk_toplam_tutar + g.mesai_toplam_tutar) *
                (1 + CASE WHEN m.faturali_mi = 1 THEN 0.10 ELSE 0 END))
            FROM gunluk_yemek_verileri g WHERE g.musteri_id = m.id
        ), 0) AS toplam_hizmet,
        COALESCE((SELECT SUM(t.tutar) FROM tahsilatlar t WHERE t.musteri_id = m.id), 0) AS toplam_odeme,
        GREATEST(0, m.devreden_borc + COALESCE((
            SELECT SUM((g.gunluk_toplam_tutar + g.mesai_toplam_tutar) *
                (1 + CASE WHEN m.faturali_mi = 1 THEN 0.10 ELSE 0 END))
            FROM gunluk_yemek_verileri g WHERE g.musteri_id = m.id
        ), 0) - COALESCE((SELECT SUM(t.tutar) FROM tahsilatlar t WHERE t.musteri_id = m.id), 0)) AS acik_borc
    FROM musteriler m
    ORDER BY " . $siralama_sql[$siralama]
)->fetchAll();

$birakilmis_borclular = array_values(array_filter($musteriler, function (array $musteri): bool {
    return !(bool)$musteri['aktif_mi'] && (float)$musteri['acik_borc'] > 0;
}));
$musteriler = array_values(array_filter($musteriler, function (array $musteri): bool {
    return (bool)$musteri['aktif_mi'];
}));

require_once 'includes/header.php';
?>

<h1 class="text-2xl font-bold text-slate-800 mb-6">Müşteri Yönetimi</h1>

<?php if ($hata): ?>
    <div class="bg-red-50 text-red-600 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($hata) ?></div>
<?php endif; ?>
<?php if ($basari): ?>
    <div class="bg-emerald-50 text-emerald-700 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($basari) ?></div>
<?php endif; ?>

<div class="bg-white rounded-2xl shadow-sm p-5 mb-6">
    <h2 class="text-base font-semibold text-slate-700 mb-4">Yeni Müşteri Ekle</h2>
    <form method="POST" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

        <div>
            <label class="block text-sm text-gray-600 mb-1">Şirket İsmi *</label>
            <input type="text" name="sirket_ismi" required
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Şahıs Adı</label>
            <input type="text" name="sahis_adi"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Telefon</label>
            <input type="text" name="telefon"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">E-posta</label>
            <input type="email" name="eposta"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Yemek Fiyatı (₺) *</label>
            <input type="text" name="anlasilan_yemek_fiyati" required placeholder="Örn: 45.00"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Mesai Yemeği Fiyatı (₺)</label>
            <input type="text" name="mesai_yemek_fiyati" placeholder="Örn: 55.00"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Varsayılan Kişi Sayısı</label>
            <input type="number" name="varsayilan_kisi_sayisi" min="0" step="1" value="0"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
            <p class="text-xs text-gray-400 mt-1">Günlük girişte başlangıç adedi olarak gelir.</p>
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Devreden / Eski Borç (₺)</label>
            <input type="text" name="devreden_borc" value="0" placeholder="Örn: 60000"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
            <p class="text-xs text-gray-400 mt-1">Sistem öncesinden kalan müşteri borcu.</p>
        </div>

        <div class="lg:col-span-3">
            <label class="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input type="checkbox" name="faturali_mi" value="1" class="w-4 h-4 accent-amber-600">
                Faturalı müşteri
            </label>
            <label class="ml-5 inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input type="checkbox" name="aktif_mi" value="1" checked class="w-4 h-4 accent-amber-600">
                Aktif müşteri (günlük yemek listesinde görünsün)
            </label>
        </div>

        <div class="lg:col-span-3">
            <label class="block text-sm text-gray-600 mb-1">Adres</label>
            <textarea name="adres" rows="2"
                      class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></textarea>
        </div>

        <div class="lg:col-span-3">
            <button type="submit" name="ekle"
                    class="bg-amber-600 hover:bg-amber-700 active:scale-[0.98] text-white font-medium px-5 py-2.5 rounded-xl transition">
                Müşteri Ekle
            </button>
        </div>

    </form>
</div>

<div class="bg-white rounded-2xl shadow-sm overflow-hidden">
    <form method="GET" class="px-5 pt-5 pb-3 flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
        <h2 class="text-base font-semibold text-slate-700">Aktif Müşteriler</h2>
        <div class="relative w-full sm:w-80">
            <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-4.35-4.35m1.85-5.65a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z" />
            </svg>
            <input id="musteriArama" type="search" placeholder="Müşteri, yetkili veya telefon ara"
                   class="w-full border border-slate-200 rounded-xl pl-9 pr-3 py-2 text-sm focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>
        <select name="siralama" onchange="this.form.submit()"
                class="border border-slate-200 rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-amber-400 focus:outline-none">
            <option value="yeni" <?= $siralama === 'yeni' ? 'selected' : '' ?>>En yeni kayıtlar</option>
            <option value="eski" <?= $siralama === 'eski' ? 'selected' : '' ?>>En eski kayıtlar</option>
            <option value="ad_artan" <?= $siralama === 'ad_artan' ? 'selected' : '' ?>>Firma adı (A–Z)</option>
            <option value="ad_azalan" <?= $siralama === 'ad_azalan' ? 'selected' : '' ?>>Firma adı (Z–A)</option>
            <option value="borc_coktan_aza" <?= $siralama === 'borc_coktan_aza' ? 'selected' : '' ?>>Açık borç (çoktan aza)</option>
            <option value="odeme_coktan_aza" <?= $siralama === 'odeme_coktan_aza' ? 'selected' : '' ?>>Ödeme (çoktan aza)</option>
        </select>
    </form>
    <div class="hidden md:block overflow-x-auto">
        <table class="w-full text-sm text-left">
            <thead class="text-slate-400 uppercase text-xs">
                <tr>
                    <th class="px-5 py-3">Şirket</th>
                    <th class="px-5 py-3">Yetkili</th>
                    <th class="px-5 py-3">Telefon</th>
                    <th class="px-5 py-3">Toplam Borç</th>
                    <th class="px-5 py-3">Toplam Ödeme</th>
                    <th class="px-5 py-3">Açık Borç</th>
                    <th class="px-5 py-3">Yemek Fiyatı</th>
                    <th class="px-5 py-3">Mesai Fiyatı</th>
                    <th class="px-5 py-3">Kayıt Tarihi</th>
                    <th class="px-5 py-3"></th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
            <?php foreach ($musteriler as $m): ?>
                <tr class="musteri-satiri hover:bg-amber-50/50" data-arama="<?= h($m['sirket_ismi'] . ' ' . $m['sahis_adi'] . ' ' . $m['telefon']) ?>">
                    <td class="px-5 py-3 font-medium">
                        <a href="musteri_detay.php?id=<?= (int)$m['id'] ?>" class="text-amber-700 hover:underline">
                            <?= h($m['sirket_ismi']) ?>
                        </a>
                        <?php if ($m['faturali_mi']): ?>
                            <span class="ml-2 inline-flex rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700">Faturalı</span>
                        <?php endif; ?>
                    </td>
                    <td class="px-5 py-3 text-slate-600"><?= h($m['sahis_adi']) ?></td>
                    <td class="px-5 py-3 text-slate-600"><?= h($m['telefon']) ?></td>
                    <td class="px-5 py-3 text-slate-600"><?= format_para($m['toplam_hizmet']) ?></td>
                    <td class="px-5 py-3 text-emerald-700 font-medium"><?= format_para($m['toplam_odeme']) ?></td>
                    <td class="px-5 py-3 <?= $m['acik_borc'] > 0 ? 'text-rose-600 font-semibold' : 'text-slate-500' ?>"><?= format_para($m['acik_borc']) ?></td>
                    <td class="px-5 py-3 text-slate-600"><?= format_para($m['anlasilan_yemek_fiyati']) ?></td>
                    <td class="px-5 py-3 text-slate-600"><?= $m['mesai_yemek_fiyati'] > 0 ? format_para($m['mesai_yemek_fiyati']) : '—' ?></td>
                    <td class="px-5 py-3 text-slate-400"><?= date('d.m.Y', strtotime($m['kayit_tarihi'])) ?></td>
                    <td class="px-5 py-3 text-right">
                        <form method="POST" class="inline">
                            <input type="hidden" name="musteri_id" value="<?= (int)$m['id'] ?>">
                            <input type="hidden" name="faturali_mi" value="<?= $m['faturali_mi'] ? 0 : 1 ?>">
                            <button type="submit" name="fatura_durum_degistir" class="text-violet-700 hover:underline text-xs font-medium mr-2"><?= $m['faturali_mi'] ? 'Fatura Etiketini Kaldır' : 'Faturalı Yap' ?></button>
                        </form>
                        <form method="POST" class="inline" onsubmit="return confirm('Bu müşteri ve ona bağlı günlük giriş, tahsilat ve ekstre kayıtları kalıcı olarak silinecek. Devam edilsin mi?');">
                            <input type="hidden" name="musteri_id" value="<?= (int)$m['id'] ?>">
                            <button type="submit" name="sil" class="text-rose-600 hover:underline text-xs font-medium">Sil</button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            <?php if (empty($musteriler)): ?>
                <tr><td colspan="10" class="px-5 py-6 text-center text-gray-400">Henüz müşteri eklenmedi.</td></tr>
            <?php endif; ?>
            <tr id="aramaSonucYok" class="hidden"><td colspan="10" class="px-5 py-6 text-center text-gray-400">Aramanızla eşleşen müşteri bulunamadı.</td></tr>
            </tbody>
        </table>
    </div>

    <div class="md:hidden px-4 pb-4 space-y-3">
        <?php foreach ($musteriler as $m): ?>
            <article class="musteri-satiri rounded-[22px] border border-slate-100 border-l-4 border-l-amber-700 bg-white p-4 shadow-sm" data-arama="<?= h($m['sirket_ismi'] . ' ' . $m['sahis_adi'] . ' ' . $m['telefon']) ?>">
                <div class="flex items-start gap-3">
                    <div class="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-sm font-bold text-amber-700">
                        <?= h(mb_strtoupper(mb_substr($m['sirket_ismi'], 0, 2, 'UTF-8'), 'UTF-8')) ?>
                    </div>
                    <div class="min-w-0 flex-1">
                        <a href="musteri_detay.php?id=<?= (int)$m['id'] ?>" class="block truncate font-semibold text-slate-800"><?= h($m['sirket_ismi']) ?></a>
                        <?php if ($m['sahis_adi']): ?><p class="mt-0.5 truncate text-xs text-slate-500"><?= h($m['sahis_adi']) ?></p><?php endif; ?>
                    </div>
                    <?php if ($m['faturali_mi']): ?><span class="shrink-0 rounded-full bg-violet-100 px-2 py-1 text-[11px] font-semibold text-violet-700">Faturalı</span><?php endif; ?>
                </div>
                <?php if ($m['telefon']): ?><p class="mt-3 text-sm text-slate-500">☎ &nbsp;<?= h($m['telefon']) ?></p><?php endif; ?>
                <div class="mt-2 space-y-1 text-sm">
                    <p class="text-slate-600">Toplam borç: <span class="font-semibold text-slate-800"><?= format_para($m['toplam_hizmet']) ?></span></p>
                    <p class="text-slate-600">Toplam ödeme: <span class="font-semibold text-emerald-700"><?= format_para($m['toplam_odeme']) ?></span></p>
                    <p class="text-slate-600">Açık borç: <span class="font-bold <?= $m['acik_borc'] > 0 ? 'text-rose-600' : 'text-slate-500' ?>"><?= format_para($m['acik_borc']) ?></span></p>
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                    <span class="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-800">Yemek <?= format_para($m['anlasilan_yemek_fiyati']) ?></span>
                    <?php if ($m['mesai_yemek_fiyati'] > 0): ?><span class="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">Mesai <?= format_para($m['mesai_yemek_fiyati']) ?></span><?php endif; ?>
                </div>
                <div class="mt-3 flex items-center gap-4 border-t border-slate-100 pt-3 text-sm">
                    <a href="musteri_detay.php?id=<?= (int)$m['id'] ?>" class="font-medium text-amber-700">✎ Düzenle / Detay</a>
                    <form method="POST" class="ml-auto"><input type="hidden" name="musteri_id" value="<?= (int)$m['id'] ?>"><input type="hidden" name="faturali_mi" value="<?= $m['faturali_mi'] ? 0 : 1 ?>"><button type="submit" name="fatura_durum_degistir" class="text-violet-700"><?= $m['faturali_mi'] ? 'Faturayı Kaldır' : 'Faturalı Yap' ?></button></form>
                    <form method="POST" onsubmit="return confirm('Bu müşteri ve ona bağlı günlük giriş, tahsilat ve ekstre kayıtları kalıcı olarak silinecek. Devam edilsin mi?');"><input type="hidden" name="musteri_id" value="<?= (int)$m['id'] ?>"><button type="submit" name="sil" class="text-rose-600">Sil</button></form>
                </div>
            </article>
        <?php endforeach; ?>
        <?php if (empty($musteriler)): ?><p class="py-6 text-center text-sm text-gray-400">Henüz müşteri eklenmedi.</p><?php endif; ?>
        <p id="aramaSonucYokMobil" class="hidden py-6 text-center text-sm text-gray-400">Aramanızla eşleşen müşteri bulunamadı.</p>
    </div>
</div>

<?php if ($birakilmis_borclular): ?>
<section class="mt-6 bg-white rounded-2xl shadow-sm p-5">
    <div class="mb-4">
        <h2 class="text-base font-semibold text-rose-700">Bırakılmış Ama Borcu Olanlar</h2>
        <p class="mt-1 text-sm text-slate-500">Bu müşteriler günlük yemek girişine gelmez; yalnızca borç ve tahsilat takibi için burada durur.</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <?php foreach ($birakilmis_borclular as $m): ?>
            <article class="musteri-satiri rounded-xl border border-rose-100 border-l-4 border-l-rose-500 bg-rose-50/30 p-4" data-arama="<?= h($m['sirket_ismi'] . ' ' . $m['sahis_adi'] . ' ' . $m['telefon']) ?>">
                <div class="flex items-start justify-between gap-3">
                    <div>
                        <a href="musteri_detay.php?id=<?= (int)$m['id'] ?>" class="font-semibold text-slate-800 hover:text-amber-700"><?= h($m['sirket_ismi']) ?></a>
                        <p class="mt-1 text-sm text-slate-500"><?= h($m['sahis_adi']) ?><?= $m['telefon'] ? ' · ' . h($m['telefon']) : '' ?></p>
                    </div>
                    <span class="rounded-full bg-slate-200 px-2 py-1 text-xs font-medium text-slate-600">Pasif</span>
                </div>
                <div class="mt-4 grid grid-cols-3 gap-2 text-center">
                    <div class="rounded-lg bg-white p-2"><p class="text-[10px] uppercase text-slate-400">Toplam Borç</p><p class="mt-1 text-xs font-semibold text-slate-700"><?= format_para($m['toplam_hizmet']) ?></p></div>
                    <div class="rounded-lg bg-white p-2"><p class="text-[10px] uppercase text-slate-400">Ödeme</p><p class="mt-1 text-xs font-semibold text-emerald-700"><?= format_para($m['toplam_odeme']) ?></p></div>
                    <div class="rounded-lg bg-white p-2"><p class="text-[10px] uppercase text-slate-400">Açık Borç</p><p class="mt-1 text-xs font-bold text-rose-600"><?= format_para($m['acik_borc']) ?></p></div>
                </div>
                <div class="mt-3 flex justify-end"><a href="musteri_detay.php?id=<?= (int)$m['id'] ?>" class="text-sm font-medium text-amber-700">Tahsilat / Detay Aç</a></div>
            </article>
        <?php endforeach; ?>
    </div>
</section>
<?php endif; ?>

<script>
document.getElementById('musteriArama')?.addEventListener('input', function () {
    const ara = this.value.trim().toLocaleLowerCase('tr-TR');
    let bulunan = 0;
    document.querySelectorAll('.musteri-satiri').forEach(function (satir) {
        const metin = satir.dataset.arama.toLocaleLowerCase('tr-TR');
        const gorunsun = !ara || metin.includes(ara);
        satir.classList.toggle('hidden', !gorunsun);
        if (gorunsun) bulunan++;
    });
    document.getElementById('aramaSonucYok')?.classList.toggle('hidden', bulunan > 0 || !ara);
    document.getElementById('aramaSonucYokMobil')?.classList.toggle('hidden', bulunan > 0 || !ara);
});
</script>

<?php require_once 'includes/footer.php'; ?>
