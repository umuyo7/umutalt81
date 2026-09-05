<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';

$id = (int)($_GET['id'] ?? 0);

$stmt = $pdo->prepare("SELECT * FROM musteriler WHERE id = ?");
$stmt->execute([$id]);
$musteri = $stmt->fetch();

if (!$musteri) {
    die('Müşteri bulunamadı.');
}

$basari = '';
$hata = '';

// --- Müşteri bilgilerini sonradan düzenleme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['musteri_guncelle'])) {
    $sirket_ismi = trim($_POST['sirket_ismi'] ?? '');
    $sahis_adi = trim($_POST['sahis_adi'] ?? '');
    $telefon = trim($_POST['telefon'] ?? '');
    $eposta = trim($_POST['eposta'] ?? '');
    $adres = trim($_POST['adres'] ?? '');
    $normalFiyatRaw = str_replace(',', '.', trim($_POST['anlasilan_yemek_fiyati'] ?? '0'));
    $mesaiFiyatRaw = str_replace(',', '.', trim($_POST['mesai_yemek_fiyati'] ?? '0'));
    $varsayilanKisiSayisi = (int)($_POST['varsayilan_kisi_sayisi'] ?? 0);
    $devredenBorcRaw = str_replace(',', '.', trim($_POST['devreden_borc'] ?? '0'));
    $faturali_mi = isset($_POST['faturali_mi']) ? 1 : 0;
    $aktif_mi = isset($_POST['aktif_mi']) ? 1 : 0;

    if ($sirket_ismi === '') {
        $hata = 'Şirket ismi zorunludur.';
    } elseif (!is_numeric($normalFiyatRaw) || (float)$normalFiyatRaw < 0 || !is_numeric($mesaiFiyatRaw) || (float)$mesaiFiyatRaw < 0 || $varsayilanKisiSayisi < 0 || !is_numeric($devredenBorcRaw) || (float)$devredenBorcRaw < 0) {
        $hata = 'Yemek fiyatlarını, kişi sayısını ve devreden borcu geçerli sayı olarak giriniz.';
    } else {
        $stmt = $pdo->prepare("\n            UPDATE musteriler\n            SET sirket_ismi = ?, sahis_adi = ?, telefon = ?, eposta = ?, adres = ?,\n                anlasilan_yemek_fiyati = ?, mesai_yemek_fiyati = ?, varsayilan_kisi_sayisi = ?, faturali_mi = ?, devreden_borc = ?, aktif_mi = ?\n            WHERE id = ?\n        ");
        $stmt->execute([$sirket_ismi, $sahis_adi, $telefon, $eposta, $adres, (float)$normalFiyatRaw, (float)$mesaiFiyatRaw, $varsayilanKisiSayisi, $faturali_mi, (float)$devredenBorcRaw, $aktif_mi, $id]);
        $basari = 'Müşteri bilgileri güncellendi.';
        $stmt = $pdo->prepare("SELECT * FROM musteriler WHERE id = ?");
        $stmt->execute([$id]);
        $musteri = $stmt->fetch();
    }
}

// --- Yeni ödeme (tahsilat) ekleme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['odeme_ekle'])) {
    $odeme_tarih = $_POST['odeme_tarih'] ?? date('Y-m-d');
    $odeme_tutar = str_replace(',', '.', trim($_POST['odeme_tutar'] ?? '0'));
    $aciklama    = trim($_POST['aciklama'] ?? '');

    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $odeme_tarih)) {
        $odeme_tarih = date('Y-m-d');
    }

    if (is_numeric($odeme_tutar) && (float)$odeme_tutar > 0) {
        $stmt = $pdo->prepare(
            "INSERT INTO tahsilatlar (musteri_id, tarih, tutar, aciklama) VALUES (?, ?, ?, ?)"
        );
        $stmt->execute([$id, $odeme_tarih, (float)$odeme_tutar, $aciklama]);
        $basari = 'Ödeme başarıyla kaydedildi.';
    }
}

// --- Oluşturulmuş ekstreyi silme ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['ekstre_sil'])) {
    $ekstre_id = (int)($_POST['ekstre_id'] ?? 0);
    $stmt = $pdo->prepare('DELETE FROM ekstreler WHERE id = ? AND musteri_id = ?');
    $stmt->execute([$ekstre_id, $id]);
    $basari = $stmt->rowCount() ? 'Ekstre PDF geçmişinden silindi.' : 'Silinecek ekstre bulunamadı.';
}

// Yemek hizmet dökümü
$stmt = $pdo->prepare("SELECT * FROM gunluk_yemek_verileri WHERE musteri_id = ? ORDER BY tarih DESC");
$stmt->execute([$id]);
$yemekler = $stmt->fetchAll();

// Ödeme dökümü
$stmt = $pdo->prepare("SELECT * FROM tahsilatlar WHERE musteri_id = ? ORDER BY tarih DESC");
$stmt->execute([$id]);
$odemeler = $stmt->fetchAll();

// Geçmiş ekstreler (PDF'ler)
$stmt = $pdo->prepare("SELECT * FROM ekstreler WHERE musteri_id = ? ORDER BY id DESC");
$stmt->execute([$id]);
$ekstreler = $stmt->fetchAll();

$toplam_normal  = array_sum(array_column($yemekler, 'gunluk_toplam_tutar'));
$toplam_mesai   = array_sum(array_column($yemekler, 'mesai_toplam_tutar'));
$toplam_hizmet  = $toplam_normal + $toplam_mesai;
$devreden_borc  = (float)$musteri['devreden_borc'];
$toplam_odeme   = array_sum(array_column($odemeler, 'tutar'));
$bakiye         = $devreden_borc + $toplam_hizmet - $toplam_odeme;

require_once 'includes/header.php';
?>

<div class="flex items-center gap-3 mb-6">
    <a href="musteriler.php" class="text-slate-500 hover:text-slate-800 p-2 -ml-2 rounded-lg hover:bg-slate-100 transition">
        <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
    </a>
    <h1 class="text-2xl font-bold text-slate-800 flex-1">Müşteri Detayı</h1>
    <a href="musteri_detay.php?id=<?= (int)$id ?>&duzenle=1" class="text-slate-600 hover:text-slate-800 text-sm font-medium px-4 py-2.5 rounded-xl border border-slate-200 transition">Düzenle</a>
    <a href="ekstre_olustur.php?musteri_id=<?= (int)$id ?>"
       class="bg-emerald-600 hover:bg-emerald-700 active:scale-[0.98] text-white text-sm font-medium px-4 py-2.5 rounded-xl transition flex items-center gap-1.5">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        Ekstre / Fatura Oluştur (PDF)
    </a>
</div>

<?php if ($hata): ?>
    <div class="bg-red-50 text-red-600 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($hata) ?></div>
<?php endif; ?>
<?php if ($basari): ?>
    <div class="bg-emerald-50 text-emerald-700 px-4 py-3 rounded-xl mb-4 text-sm"><?= h($basari) ?></div>
<?php endif; ?>

<div class="bg-white rounded-2xl shadow-sm p-5 mb-6">
    <div class="flex items-center gap-2">
        <h2 class="text-xl font-bold text-slate-800"><?= h($musteri['sirket_ismi']) ?></h2>
        <?php if ($musteri['faturali_mi']): ?>
            <span class="inline-flex rounded-full bg-violet-100 px-2 py-1 text-xs font-semibold text-violet-700">Faturalı Müşteri</span>
        <?php endif; ?>
        <?php if (!$musteri['aktif_mi']): ?>
            <span class="inline-flex rounded-full bg-slate-200 px-2 py-1 text-xs font-semibold text-slate-600">Pasif Müşteri</span>
        <?php endif; ?>
    </div>
    <p class="text-gray-500 text-sm mt-1">
        <?= h($musteri['sahis_adi']) ?><?= $musteri['telefon'] ? ' · ' . h($musteri['telefon']) : '' ?><?= $musteri['eposta'] ? ' · ' . h($musteri['eposta']) : '' ?>
    </p>
    <?php if ($musteri['adres']): ?>
        <p class="text-gray-500 text-sm mt-1"><?= h($musteri['adres']) ?></p>
    <?php endif; ?>
    <p class="text-sm text-gray-500 mt-2">
        Yemek Fiyatı:
        <span class="font-medium text-slate-700"><?= format_para($musteri['anlasilan_yemek_fiyati']) ?></span>
        <?php if ($musteri['mesai_yemek_fiyati'] > 0): ?>
            &nbsp;·&nbsp; Mesai Fiyatı:
            <span class="font-medium text-slate-700"><?= format_para($musteri['mesai_yemek_fiyati']) ?></span>
        <?php endif; ?>
    </p>
</div>

<?php if (isset($_GET['duzenle']) || $hata): ?>
<div class="bg-white rounded-2xl shadow-sm p-5 mb-6">
    <h3 class="font-semibold text-slate-700 mb-4">Müşteri Bilgilerini Düzenle</h3>
    <form method="POST" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div><label class="block text-sm text-gray-600 mb-1">Şirket İsmi *</label><input type="text" name="sirket_ismi" required value="<?= h($musteri['sirket_ismi']) ?>" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Şahıs Adı</label><input type="text" name="sahis_adi" value="<?= h($musteri['sahis_adi']) ?>" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Telefon</label><input type="text" name="telefon" value="<?= h($musteri['telefon']) ?>" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">E-posta</label><input type="email" name="eposta" value="<?= h($musteri['eposta']) ?>" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Yemek Fiyatı (₺)</label><input type="text" name="anlasilan_yemek_fiyati" value="<?= h($musteri['anlasilan_yemek_fiyati']) ?>" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Mesai Yemeği Fiyatı (₺)</label><input type="text" name="mesai_yemek_fiyati" value="<?= h($musteri['mesai_yemek_fiyati']) ?>" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Varsayılan Kişi Sayısı</label><input type="number" min="0" step="1" name="varsayilan_kisi_sayisi" value="<?= (int)$musteri['varsayilan_kisi_sayisi'] ?>" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div><label class="block text-sm text-gray-600 mb-1">Devreden / Eski Borç (₺)</label><input type="text" name="devreden_borc" value="<?= h($musteri['devreden_borc']) ?>" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"></div>
        <div class="lg:col-span-3"><label class="block text-sm text-gray-600 mb-1">Adres</label><textarea name="adres" rows="2" class="w-full border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none"><?= h($musteri['adres']) ?></textarea></div>
        <div class="lg:col-span-3"><label class="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer"><input type="checkbox" name="faturali_mi" value="1" <?= $musteri['faturali_mi'] ? 'checked' : '' ?> class="w-4 h-4 accent-amber-600"> Faturalı müşteri</label></div>
        <div class="lg:col-span-3"><label class="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer"><input type="checkbox" name="aktif_mi" value="1" <?= $musteri['aktif_mi'] ? 'checked' : '' ?> class="w-4 h-4 accent-amber-600"> Aktif müşteri — kaldırılırsa günlük yemek listesinde görünmez.</label></div>
        <div class="lg:col-span-3 flex gap-3"><button type="submit" name="musteri_guncelle" class="bg-emerald-600 hover:bg-emerald-700 text-white font-medium px-5 py-2.5 rounded-xl transition">Değişiklikleri Kaydet</button><a href="musteri_detay.php?id=<?= (int)$id ?>" class="px-5 py-2.5 rounded-xl border border-slate-200 text-slate-600">Vazgeç</a></div>
    </form>
</div>
<?php endif; ?>

<div class="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-6">
    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-amber-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Devreden / Eski Borç</p>
        <p class="text-xl font-bold text-amber-700 mt-2"><?= format_para($devreden_borc) ?></p>
    </div>
    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-amber-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Toplam Hizmet Tutarı</p>
        <p class="text-xl font-bold text-slate-800 mt-2"><?= format_para($toplam_hizmet) ?></p>
    </div>
    <div class="bg-white rounded-2xl shadow-sm border-b-4 border-emerald-500 p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Toplam Ödeme</p>
        <p class="text-xl font-bold text-emerald-600 mt-2"><?= format_para($toplam_odeme) ?></p>
    </div>
    <div class="bg-white rounded-2xl shadow-sm border-b-4 <?= $bakiye > 0 ? 'border-rose-500' : 'border-slate-300' ?> p-5">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Güncel Bakiye</p>
        <p class="text-xl font-bold <?= $bakiye > 0 ? 'text-rose-600' : 'text-slate-800' ?> mt-2"><?= format_para($bakiye) ?></p>
    </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">

    <div class="bg-white rounded-2xl shadow-sm overflow-hidden">
        <h3 class="px-5 pt-5 pb-2 text-base font-semibold text-slate-700">Yemek Hizmet Dökümü</h3>
        <div class="overflow-x-auto">
            <table class="w-full text-sm text-left">
                <thead class="text-slate-400 text-xs uppercase">
                    <tr>
                        <th class="px-5 py-2">Tarih</th>
                        <th class="px-5 py-2">Yemek Adedi</th>
                        <th class="px-5 py-2">Mesai</th>
                        <th class="px-5 py-2">Tutar</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                <?php foreach ($yemekler as $y): ?>
                    <tr>
                        <td class="px-5 py-2"><?= date('d.m.Y', strtotime($y['tarih'])) ?></td>
                        <td class="px-5 py-2"><?= (int)$y['yemek_adedi'] ?></td>
                        <td class="px-5 py-2"><?= (int)$y['mesai_yemek_adedi'] ?: '—' ?></td>
                        <td class="px-5 py-2"><?= format_para((float)$y['gunluk_toplam_tutar'] + (float)$y['mesai_toplam_tutar']) ?></td>
                    </tr>
                <?php endforeach; ?>
                <?php if (empty($yemekler)): ?>
                    <tr><td colspan="4" class="px-5 py-4 text-center text-gray-400">Kayıt yok.</td></tr>
                <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>

    <div class="bg-white rounded-2xl shadow-sm overflow-hidden">
        <h3 class="px-5 pt-5 pb-2 text-base font-semibold text-slate-700">Ödeme (Tahsilat) Dökümü</h3>
        <div class="overflow-x-auto">
            <table class="w-full text-sm text-left">
                <thead class="text-slate-400 text-xs uppercase">
                    <tr>
                        <th class="px-5 py-2">Tarih</th>
                        <th class="px-5 py-2">Açıklama</th>
                        <th class="px-5 py-2">Tutar</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                <?php foreach ($odemeler as $o): ?>
                    <tr>
                        <td class="px-5 py-2"><?= date('d.m.Y', strtotime($o['tarih'])) ?></td>
                        <td class="px-5 py-2"><?= h($o['aciklama']) ?></td>
                        <td class="px-5 py-2 text-emerald-600"><?= format_para($o['tutar']) ?></td>
                    </tr>
                <?php endforeach; ?>
                <?php if (empty($odemeler)): ?>
                    <tr><td colspan="3" class="px-5 py-4 text-center text-gray-400">Kayıt yok.</td></tr>
                <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>

</div>

<div class="bg-white rounded-2xl shadow-sm p-5">
    <h3 class="font-semibold text-slate-700 mb-3">Yeni Ödeme (Tahsilat) Ekle</h3>
    <form method="POST" class="flex flex-wrap items-end gap-4">
        <div>
            <label class="block text-sm text-gray-600 mb-1">Tarih</label>
            <input type="date" name="odeme_tarih" value="<?= date('Y-m-d') ?>"
                   class="border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>
        <div>
            <label class="block text-sm text-gray-600 mb-1">Tutar (₺)</label>
            <input type="text" name="odeme_tutar" required placeholder="0.00"
                   class="border border-slate-200 rounded-xl px-3 py-2.5 w-32 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>
        <div>
            <label class="block text-sm text-gray-600 mb-1">Açıklama</label>
            <input type="text" name="aciklama"
                   class="border border-slate-200 rounded-xl px-3 py-2.5 focus:ring-2 focus:ring-amber-400 focus:outline-none">
        </div>
        <button type="submit" name="odeme_ekle"
                class="bg-emerald-600 hover:bg-emerald-700 active:scale-[0.98] text-white px-5 py-2.5 rounded-xl transition">
            Ödeme Kaydet
        </button>
    </form>
</div>

<div class="bg-white rounded-2xl shadow-sm overflow-hidden mt-6">
    <h3 class="px-5 pt-5 pb-2 text-base font-semibold text-slate-700">Oluşturulan Ekstreler (PDF Geçmişi)</h3>
    <div class="overflow-x-auto">
        <table class="w-full text-sm text-left">
            <thead class="text-slate-400 text-xs uppercase">
                <tr>
                    <th class="px-5 py-2">Ekstre No</th>
                    <th class="px-5 py-2">Dönem</th>
                    <th class="px-5 py-2">Dönem Toplamı</th>
                    <th class="px-5 py-2">Kalan Bakiye</th>
                    <th class="px-5 py-2">Oluşturma</th>
                    <th class="px-5 py-2"></th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
            <?php foreach ($ekstreler as $ek): ?>
                <tr class="hover:bg-amber-50/50">
                    <td class="px-5 py-2 font-medium">EKS-<?= str_pad((string)$ek['id'], 5, '0', STR_PAD_LEFT) ?></td>
                    <td class="px-5 py-2"><?= format_tarih($ek['baslama_tarihi']) ?> – <?= format_tarih($ek['bitis_tarihi']) ?></td>
                    <td class="px-5 py-2"><?= format_para($ek['donem_toplami']) ?></td>
                    <td class="px-5 py-2 font-medium"><?= format_para($ek['kalan_bakiye']) ?></td>
                    <td class="px-5 py-2 text-slate-400"><?= date('d.m.Y', strtotime($ek['olusturma_tarihi'])) ?></td>
                    <td class="px-5 py-2 text-right whitespace-nowrap">
                        <a href="ekstre_pdf.php?id=<?= (int)$ek['id'] ?>" target="_blank" class="text-amber-700 hover:underline text-xs font-medium">Özet PDF</a>
                        <span class="text-slate-300 px-1">|</span>
                        <a href="ekstre_detay_pdf.php?id=<?= (int)$ek['id'] ?>" target="_blank" class="text-emerald-700 hover:underline text-xs font-medium">Gün Gün Detay PDF</a>
                        <span class="text-slate-300 px-1">|</span>
                        <form method="POST" class="inline" onsubmit="return confirm('Bu ekstre PDF geçmişinden silinecek. Yemek ve ödeme kayıtları silinmez. Devam edilsin mi?');">
                            <input type="hidden" name="ekstre_id" value="<?= (int)$ek['id'] ?>">
                            <button type="submit" name="ekstre_sil" class="text-rose-600 hover:underline text-xs font-medium">Sil</button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            <?php if (empty($ekstreler)): ?>
                <tr><td colspan="6" class="px-5 py-6 text-center text-gray-400">Henüz ekstre oluşturulmadı.</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<?php require_once 'includes/footer.php'; ?>
