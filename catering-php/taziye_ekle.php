<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$hata = '';
$basari = '';

// --- Yeni taziye yemeği kaydı ekle ---
// Not: Taziye yemeği HER ZAMAN tek seferliktir, kayıtlı bir müşteriye
// bağlanmaz. Firma/kişi adı her seferinde serbest metin olarak girilir.
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['ekle'])) {
    $firma_adi  = trim($_POST['firma_adi'] ?? '');
    $tarih      = $_POST['tarih'] ?? date('Y-m-d');
    $adet       = (int)($_POST['adet'] ?? 0);
    $birim_raw  = str_replace(',', '.', trim($_POST['birim_fiyat'] ?? '0'));
    $aciklama   = trim($_POST['aciklama'] ?? '');

    if (!gecerli_tarih_mi($tarih)) {
        $tarih = date('Y-m-d');
    }

    if ($firma_adi === '') {
        $hata = 'Firma/kişi adı zorunludur.';
    } elseif ($adet <= 0) {
        $hata = 'Lütfen geçerli bir yemek adedi giriniz.';
    } elseif (!is_numeric($birim_raw) || (float)$birim_raw < 0) {
        $hata = 'Lütfen geçerli bir birim fiyat giriniz.';
    } else {
        $toplam = $adet * (float)$birim_raw;
        $stmt = $pdo->prepare(
            "INSERT INTO taziye_yemekleri (firma_adi, tarih, adet, birim_fiyat, toplam_tutar, aciklama)
             VALUES (?, ?, ?, ?, ?, ?)"
        );
        $stmt->execute([$firma_adi, $tarih, $adet, (float)$birim_raw, $toplam, $aciklama]);
        $basari = 'Taziye yemeği kaydı başarıyla eklendi.';
    }
}

// --- Kayıt silme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['sil'])) {
    $sil_id = (int)$_POST['sil'];
    $stmt = $pdo->prepare("DELETE FROM taziye_yemekleri WHERE id = ?");
    $stmt->execute([$sil_id]);
    $basari = 'Kayıt silindi.';
}

$kayitlar = $pdo->query("SELECT * FROM taziye_yemekleri ORDER BY tarih DESC, id DESC LIMIT 100")->fetchAll();
$genel_toplam = (float)$pdo->query("SELECT COALESCE(SUM(toplam_tutar),0) t FROM taziye_yemekleri")->fetch()['t'];

require_once 'includes/header.php';
?>

<h1 class="text-2xl font-bold text-slate-800 mb-6">Taziye Yemeği (Tek Seferlik)</h1>

<?php if ($hata): ?>
    <div class="bg-red-50 text-red-600 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($hata) ?></div>
<?php endif; ?>
<?php if ($basari): ?>
    <div class="bg-emerald-50 text-emerald-700 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($basari) ?></div>
<?php endif; ?>

<div class="bg-white rounded-2xl shadow-sm p-5 mb-6">
    <h2 class="text-base font-semibold text-slate-700 mb-1">Yeni Taziye Yemeği Kaydı</h2>
    <p class="text-xs text-gray-400 mb-4">Tek seferlik taziye yemeği siparişleri için kullanılır; kayıtlı müşteri listesiyle ilişkisi yoktur, her seferinde firma/kişi adı serbestçe yazılır.</p>
    <form method="POST" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">

        <div>
            <label class="block text-sm text-gray-600 mb-1">Firma / Kişi Adı *</label>
            <input type="text" name="firma_adi" required placeholder="Örn: Yılmaz Ailesi Taziyesi"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Tarih *</label>
            <input type="date" name="tarih" required value="<?= date('Y-m-d') ?>"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Yemek Adedi *</label>
            <input type="number" min="1" name="adet" required placeholder="Örn: 150"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Birim Fiyat (₺) *</label>
            <input type="text" name="birim_fiyat" required placeholder="Örn: 90.00"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div class="lg:col-span-4">
            <label class="block text-sm text-gray-600 mb-1">Açıklama</label>
            <input type="text" name="aciklama" placeholder="Örn: Taziye evi - Merhum ... için"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div class="lg:col-span-4">
            <button type="submit" name="ekle"
                    class="bg-amber-600 hover:bg-amber-700 active:scale-[0.98] text-white font-medium px-5 py-2.5 rounded-xl transition">
                Kaydet
            </button>
        </div>

    </form>
</div>

<div class="bg-white rounded-2xl shadow-sm overflow-hidden">
    <div class="flex items-center justify-between px-5 pt-5 pb-2">
        <h2 class="text-base font-semibold text-slate-700">Taziye Yemeği Kayıtları</h2>
        <span class="text-sm text-slate-500">Toplam: <span class="font-semibold text-slate-800"><?= format_para($genel_toplam) ?></span></span>
    </div>
    <div class="overflow-x-auto">
        <table class="w-full text-sm text-left">
            <thead class="text-slate-400 uppercase text-xs">
                <tr>
                    <th class="px-5 py-3">Tarih</th>
                    <th class="px-5 py-3">Firma / Kişi</th>
                    <th class="px-5 py-3">Adet</th>
                    <th class="px-5 py-3">Birim Fiyat</th>
                    <th class="px-5 py-3">Toplam</th>
                    <th class="px-5 py-3"></th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
            <?php foreach ($kayitlar as $k): ?>
                <tr class="hover:bg-amber-50/50">
                    <td class="px-5 py-3"><?= format_tarih($k['tarih']) ?></td>
                    <td class="px-5 py-3 font-medium">
                        <?= h($k['firma_adi']) ?>
                        <?php if ($k['aciklama']): ?><span class="block text-xs text-gray-400"><?= h($k['aciklama']) ?></span><?php endif; ?>
                    </td>
                    <td class="px-5 py-3"><?= (int)$k['adet'] ?></td>
                    <td class="px-5 py-3 text-slate-600"><?= format_para($k['birim_fiyat']) ?></td>
                    <td class="px-5 py-3 font-medium"><?= format_para($k['toplam_tutar']) ?></td>
                    <td class="px-5 py-3 text-right">
                        <a href="taziye_pdf.php?id=<?= (int)$k['id'] ?>" target="_blank" class="text-emerald-700 hover:underline text-xs font-medium mr-3">PDF</a>
                        <form method="POST" class="inline" onsubmit="return confirm('Bu kaydı silmek istediğinize emin misiniz?');">
                            <button type="submit" name="sil" value="<?= (int)$k['id'] ?>"
                                    class="text-rose-500 hover:text-rose-700 text-xs font-medium">Sil</button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            <?php if (empty($kayitlar)): ?>
                <tr><td colspan="6" class="px-5 py-6 text-center text-gray-400">Henüz taziye yemeği kaydı yok.</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<?php require_once 'includes/footer.php'; ?>
