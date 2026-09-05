<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$tarih = $_GET['tarih'] ?? date('Y-m-d');
if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $tarih)) {
    $tarih = date('Y-m-d');
}

$basari = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $form_tarih = $_POST['tarih'] ?? date('Y-m-d');
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $form_tarih)) {
        $form_tarih = date('Y-m-d');
    }
    $adetler = $_POST['adet'] ?? [];
    $mesai_adetler = $_POST['mesai_adet'] ?? [];

    $stmt_musteri = $pdo->prepare("SELECT anlasilan_yemek_fiyati, mesai_yemek_fiyati FROM musteriler WHERE id = ?");

    // musteri_id + tarih üzerindeki UNIQUE anahtar sayesinde, aynı gün için
    // tekrar kayıt gönderilirse veri eklenmez, güncellenir (upsert).
    $stmt_upsert = $pdo->prepare("
        INSERT INTO gunluk_yemek_verileri (musteri_id, tarih, yemek_adedi, gunluk_toplam_tutar, mesai_yemek_adedi, mesai_toplam_tutar)
        VALUES (?, ?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
            yemek_adedi = VALUES(yemek_adedi),
            gunluk_toplam_tutar = VALUES(gunluk_toplam_tutar),
            mesai_yemek_adedi = VALUES(mesai_yemek_adedi),
            mesai_toplam_tutar = VALUES(mesai_toplam_tutar)
    ");
    $stmt_sil = $pdo->prepare("DELETE FROM gunluk_yemek_verileri WHERE musteri_id = ? AND tarih = ?");

    $pdo->beginTransaction();
    try {
        // Bu tarih için formda görünen tüm müşterilerin id'lerini topla
        $tum_musteri_id = array_unique(array_merge(array_keys($adetler), array_keys($mesai_adetler)));

        foreach ($tum_musteri_id as $musteri_id) {
            $musteri_id = (int)$musteri_id;
            $adet = (int)($adetler[$musteri_id] ?? 0);
            $mesai_adet = (int)($mesai_adetler[$musteri_id] ?? 0);

            if ($adet <= 0 && $mesai_adet <= 0) {
                // Daha önce kayıt girilmiş bir satır 0 yapılırsa eski kaydı sil.
                $stmt_sil->execute([$musteri_id, $form_tarih]);
                continue;
            }

            $stmt_musteri->execute([$musteri_id]);
            $musteri = $stmt_musteri->fetch();
            if (!$musteri) {
                continue;
            }

            $toplam = $adet * (float)$musteri['anlasilan_yemek_fiyati'];
            $mesai_toplam = $mesai_adet * (float)$musteri['mesai_yemek_fiyati'];
            $stmt_upsert->execute([$musteri_id, $form_tarih, $adet, $toplam, $mesai_adet, $mesai_toplam]);
        }
        $pdo->commit();
        $basari = 'Günlük yemek verileri başarıyla kaydedildi.';
    } catch (Exception $e) {
        $pdo->rollBack();
        $basari = '';
    }

    $tarih = $form_tarih;
}

// Sistemdeki tüm müşteriler, seçilen sıralama ile listelenir.
$siralama = $_GET['siralama'] ?? 'ad_artan';
$siralama_sql = [
    'ad_artan' => 'sirket_ismi ASC',
    'ad_azalan' => 'sirket_ismi DESC',
    'kisi_coktan_aza' => 'varsayilan_kisi_sayisi DESC, sirket_ismi ASC',
    'kisi_azdan_coga' => 'varsayilan_kisi_sayisi ASC, sirket_ismi ASC',
];
if (!isset($siralama_sql[$siralama])) {
    $siralama = 'ad_artan';
}
$musteriler = $pdo->query("SELECT * FROM musteriler WHERE aktif_mi = 1 ORDER BY " . $siralama_sql[$siralama])->fetchAll();

// Seçilen tarih için daha önce girilmiş veriler varsa, formu onlarla doldur
$stmt_mevcut = $pdo->prepare("SELECT musteri_id, yemek_adedi, mesai_yemek_adedi FROM gunluk_yemek_verileri WHERE tarih = ?");
$stmt_mevcut->execute([$tarih]);
$mevcut_veriler = [];
$mevcut_mesai_veriler = [];
foreach ($stmt_mevcut->fetchAll() as $row) {
    $mevcut_veriler[$row['musteri_id']] = $row['yemek_adedi'];
    $mevcut_mesai_veriler[$row['musteri_id']] = $row['mesai_yemek_adedi'];
}

require_once 'includes/header.php';
?>

<h1 class="text-2xl font-bold text-slate-800 mb-6">Günlük Yemek Girişi</h1>

<?php if ($basari): ?>
    <div class="bg-emerald-50 text-emerald-700 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($basari) ?></div>
<?php endif; ?>

<form method="GET" class="bg-white rounded-2xl shadow-sm p-5 mb-6 flex flex-wrap items-end gap-4">
    <div>
        <label class="block text-sm text-gray-600 mb-1">Tarih</label>
        <input type="date" name="tarih" value="<?= h($tarih) ?>"
               class="border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
    </div>
    <button type="submit" class="bg-slate-700 hover:bg-slate-800 text-white px-4 py-2.5 rounded-xl transition">
        Tarihi Görüntüle
    </button>
    <div class="min-w-56 flex-1">
        <label class="block text-sm text-gray-600 mb-1">Müşteri Ara</label>
        <input type="search" id="musteriArama" autocomplete="off" placeholder="Firma adı yazın..."
               class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
    </div>
    <div>
        <label class="block text-sm text-gray-600 mb-1">Sıralama</label>
        <select name="siralama" onchange="this.form.submit()"
                class="border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
            <option value="ad_artan" <?= $siralama === 'ad_artan' ? 'selected' : '' ?>>Firma adı (A–Z)</option>
            <option value="ad_azalan" <?= $siralama === 'ad_azalan' ? 'selected' : '' ?>>Firma adı (Z–A)</option>
            <option value="kisi_coktan_aza" <?= $siralama === 'kisi_coktan_aza' ? 'selected' : '' ?>>Kişi sayısı (çoktan aza)</option>
            <option value="kisi_azdan_coga" <?= $siralama === 'kisi_azdan_coga' ? 'selected' : '' ?>>Kişi sayısı (azdan çoğa)</option>
        </select>
    </div>
    <?php if (!empty($mevcut_veriler)): ?>
        <span class="text-sm text-amber-600">Bu tarih için daha önce girilmiş veriler mevcut, aşağıda düzenleyebilirsiniz.</span>
    <?php endif; ?>
</form>

<form method="POST" class="hidden md:block">
    <input type="hidden" name="tarih" value="<?= h($tarih) ?>">

    <div class="bg-white rounded-2xl shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-sm text-left">
                <thead class="text-slate-400 uppercase text-xs">
                    <tr>
                        <th class="px-5 py-3">Müşteri</th>
                        <th class="px-5 py-3">Yemek Fiyatı</th>
                        <th class="px-5 py-3">Yemek Adedi</th>
                        <th class="px-5 py-3">Mesai Fiyatı</th>
                        <th class="px-5 py-3">Mesai Yemeği Adedi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                <?php foreach ($musteriler as $m): ?>
                    <tr class="musteri-satiri hover:bg-amber-50/50">
                        <td class="px-5 py-3 font-medium"><?= h($m['sirket_ismi']) ?></td>
                        <td class="px-5 py-3 text-slate-600"><?= format_para($m['anlasilan_yemek_fiyati']) ?></td>
                        <td class="px-5 py-3">
                            <input type="number" min="0" step="1"
                                   name="adet[<?= (int)$m['id'] ?>]"
                                   value="<?= array_key_exists($m['id'], $mevcut_veriler) ? (int)$mevcut_veriler[$m['id']] : (int)$m['varsayilan_kisi_sayisi'] ?>"
                                   class="w-24 border border-slate-200 rounded-xl px-3 py-1.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
                        </td>
                        <td class="px-5 py-3 text-slate-600"><?= $m['mesai_yemek_fiyati'] > 0 ? format_para($m['mesai_yemek_fiyati']) : '—' ?></td>
                        <td class="px-5 py-3">
                            <input type="number" min="0" step="1"
                                   name="mesai_adet[<?= (int)$m['id'] ?>]"
                                   value="<?= (int)($mevcut_mesai_veriler[$m['id']] ?? 0) ?>"
                                   class="w-24 border border-slate-200 rounded-xl px-3 py-1.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
                        </td>
                    </tr>
                <?php endforeach; ?>
                <?php if (empty($musteriler)): ?>
                    <tr><td colspan="5" class="px-5 py-6 text-center text-gray-400">Müşteri bulunamadı.</td></tr>
                <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>

    <div class="mt-4">
        <button type="submit"
                class="bg-amber-600 hover:bg-amber-700 active:scale-[0.98] text-white font-medium px-6 py-3 rounded-xl transition">
            Kaydet
        </button>
    </div>
</form>

<form method="POST" class="md:hidden">
    <input type="hidden" name="tarih" value="<?= h($tarih) ?>">
    <div class="space-y-3">
        <?php foreach ($musteriler as $m): ?>
            <article class="musteri-satiri bg-white rounded-2xl shadow-sm p-4" data-arama="<?= h($m['sirket_ismi']) ?>">
                <div class="flex items-start justify-between gap-3 mb-4">
                    <div>
                        <h2 class="font-semibold text-slate-800"><?= h($m['sirket_ismi']) ?></h2>
                        <p class="text-xs text-slate-500 mt-1">Varsayılan kişi: <?= (int)$m['varsayilan_kisi_sayisi'] ?></p>
                    </div>
                    <?php if ($m['faturali_mi']): ?><span class="rounded-full bg-violet-100 px-2 py-1 text-xs font-medium text-violet-700">Faturalı</span><?php endif; ?>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs text-slate-500 mb-1">Yemek Adedi · <?= format_para($m['anlasilan_yemek_fiyati']) ?></label>
                        <input type="number" min="0" step="1" name="adet[<?= (int)$m['id'] ?>]"
                               value="<?= array_key_exists($m['id'], $mevcut_veriler) ? (int)$mevcut_veriler[$m['id']] : (int)$m['varsayilan_kisi_sayisi'] ?>"
                               class="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-lg font-semibold focus:ring-2 focus:ring-amber-400 focus:outline-none">
                    </div>
                    <div>
                        <label class="block text-xs text-slate-500 mb-1">Mesai · <?= $m['mesai_yemek_fiyati'] > 0 ? format_para($m['mesai_yemek_fiyati']) : 'Fiyat yok' ?></label>
                        <input type="number" min="0" step="1" name="mesai_adet[<?= (int)$m['id'] ?>]"
                               value="<?= (int)($mevcut_mesai_veriler[$m['id']] ?? 0) ?>"
                               class="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-lg font-semibold focus:ring-2 focus:ring-amber-400 focus:outline-none">
                    </div>
                </div>
            </article>
        <?php endforeach; ?>
        <?php if (empty($musteriler)): ?><p class="py-8 text-center text-sm text-gray-400">Müşteri bulunamadı.</p><?php endif; ?>
        <p id="gunlukAramaSonucYok" class="hidden py-8 text-center text-sm text-gray-400">Aramanızla eşleşen müşteri bulunamadı.</p>
    </div>
    <div class="sticky bottom-3 mt-4">
        <button type="submit" class="w-full bg-amber-600 hover:bg-amber-700 text-white font-medium px-6 py-3 rounded-xl shadow-lg transition">Günlük Girişi Kaydet</button>
    </div>
</form>

<script>
const musteriArama = document.getElementById('musteriArama');
if (musteriArama) {
    musteriArama.addEventListener('input', function () {
        const aranan = this.value.trim().toLocaleLowerCase('tr-TR');
        let bulunan = 0;
        document.querySelectorAll('.musteri-satiri').forEach(function (satir) {
            satir.hidden = aranan !== '' && !satir.textContent.toLocaleLowerCase('tr-TR').includes(aranan);
            if (!satir.hidden) bulunan++;
        });
        document.getElementById('gunlukAramaSonucYok')?.classList.toggle('hidden', bulunan > 0 || aranan === '');
    });
}
</script>

<?php require_once 'includes/footer.php'; ?>
