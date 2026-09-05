<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$hata = '';
$basari = '';

// --- Yeni taziye yemeği kaydı ekleme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['ekle'])) {
    $musteri_id  = (int)($_POST['musteri_id'] ?? 0);
    $tarih       = $_POST['tarih'] ?? date('Y-m-d');
    $aciklama    = trim($_POST['aciklama'] ?? '');
    $adet        = (int)($_POST['adet'] ?? 0);
    $birim_fiyat_raw = str_replace(',', '.', trim($_POST['birim_fiyat'] ?? '0'));

    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $tarih)) {
        $tarih = date('Y-m-d');
    }

    if ($musteri_id <= 0) {
        $hata = 'Lütfen bir müşteri seçiniz.';
    } elseif ($adet <= 0) {
        $hata = 'Lütfen geçerli bir adet giriniz.';
    } elseif (!is_numeric($birim_fiyat_raw) || (float)$birim_fiyat_raw < 0) {
        $hata = 'Lütfen geçerli bir birim fiyat giriniz.';
    } else {
        $birim_fiyat = (float)$birim_fiyat_raw;
        $tutar = $adet * $birim_fiyat;
        $stmt = $pdo->prepare(
            "INSERT INTO taziye_yemekleri (musteri_id, tarih, aciklama, adet, birim_fiyat, tutar)
             VALUES (?, ?, ?, ?, ?, ?)"
        );
        $stmt->execute([$musteri_id, $tarih, $aciklama, $adet, $birim_fiyat, $tutar]);
        $basari = 'Taziye yemeği kaydı başarıyla eklendi.';
    }
}

// --- Kayıt silme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['sil'])) {
    $sil_id = (int)($_POST['sil_id'] ?? 0);
    if ($sil_id > 0) {
        $stmt = $pdo->prepare("DELETE FROM taziye_yemekleri WHERE id = ?");
        $stmt->execute([$sil_id]);
        $basari = 'Kayıt silindi.';
    }
}

$musteriler = $pdo->query("SELECT id, sirket_ismi FROM musteriler ORDER BY sirket_ismi ASC")->fetchAll();

$kayitlar = $pdo->query("
    SELECT t.*, m.sirket_ismi
    FROM taziye_yemekleri t
    JOIN musteriler m ON m.id = t.musteri_id
    ORDER BY t.tarih DESC, t.id DESC
    LIMIT 100
")->fetchAll();

require_once 'includes/header.php';
?>

<h1 class="text-2xl font-bold text-slate-800 mb-1">Taziye Yemekleri</h1>
<p class="text-sm text-gray-500 mb-6">Tek seferlik, fiyatı değişebilen taziye yemeği kayıtları burada tutulur.</p>

<?php if ($hata): ?>
    <div class="bg-red-50 text-red-600 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($hata) ?></div>
<?php endif; ?>
<?php if ($basari): ?>
    <div class="bg-emerald-50 text-emerald-700 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($basari) ?></div>
<?php endif; ?>

<div class="bg-white rounded-2xl shadow-sm p-5 mb-6">
    <h2 class="text-base font-semibold text-slate-700 mb-4">Yeni Taziye Yemeği Kaydı</h2>
    <form method="POST" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">

        <div class="lg:col-span-2">
            <label class="block text-sm text-gray-600 mb-1">Müşteri *</label>
            <select name="musteri_id" required
                    class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
                <option value="">Seçiniz</option>
                <?php foreach ($musteriler as $m): ?>
                    <option value="<?= (int)$m['id'] ?>"><?= h($m['sirket_ismi']) ?></option>
                <?php endforeach; ?>
            </select>
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Tarih *</label>
            <input type="date" name="tarih" required value="<?= date('Y-m-d') ?>"
                   class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>

        <div>
            <label class="block text-sm text-gray-600 mb-1">Adet *</label>
            <input type="number" min="1" step="1" name="adet" required
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

        <div class="lg:col-span-5">
            <button type="submit" name="ekle"
                    class="bg-amber-600 hover:bg-amber-700 active:scale-[0.98] text-white font-medium px-5 py-2.5 rounded-xl transition">
                Kaydet
            </button>
        </div>

    </form>
</div>

<div class="bg-white rounded-2xl shadow-sm overflow-hidden">
    <h2 class="px-5 pt-5 pb-2 text-base font-semibold text-slate-700">Son Kayıtlar</h2>
    <div class="overflow-x-auto">
        <table class="w-full text-sm text-left">
            <thead class="text-slate-400 uppercase text-xs">
                <tr>
                    <th class="px-5 py-3">Tarih</th>
                    <th class="px-5 py-3">Müşteri</th>
                    <th class="px-5 py-3">Açıklama</th>
                    <th class="px-5 py-3">Adet</th>
                    <th class="px-5 py-3">Birim Fiyat</th>
                    <th class="px-5 py-3">Tutar</th>
                    <th class="px-5 py-3"></th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
            <?php foreach ($kayitlar as $k): ?>
                <tr class="hover:bg-amber-50/50">
                    <td class="px-5 py-3"><?= date('d.m.Y', strtotime($k['tarih'])) ?></td>
                    <td class="px-5 py-3 font-medium">
                        <a href="musteri_detay.php?id=<?= (int)$k['musteri_id'] ?>" class="text-amber-700 hover:underline">
                            <?= h($k['sirket_ismi']) ?>
                        </a>
                    </td>
                    <td class="px-5 py-3 text-slate-600"><?= h($k['aciklama']) ?></td>
                    <td class="px-5 py-3"><?= (int)$k['adet'] ?></td>
                    <td class="px-5 py-3 text-slate-600"><?= format_para($k['birim_fiyat']) ?></td>
                    <td class="px-5 py-3 font-medium"><?= format_para($k['tutar']) ?></td>
                    <td class="px-5 py-3 text-right">
                        <form method="POST" onsubmit="return confirm('Bu kaydı silmek istediğinize emin misiniz?');">
                            <input type="hidden" name="sil_id" value="<?= (int)$k['id'] ?>">
                            <button type="submit" name="sil" class="text-slate-400 hover:text-red-600 transition p-1" title="Sil">
                                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            <?php if (empty($kayitlar)): ?>
                <tr><td colspan="7" class="px-5 py-6 text-center text-gray-400">Henüz taziye yemeği kaydı yok.</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<?php require_once 'includes/footer.php'; ?>
