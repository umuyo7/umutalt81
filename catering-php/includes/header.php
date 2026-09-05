<?php
if (session_status() === PHP_SESSION_NONE) {
    session_start();
}
$__mevcut_sayfa = basename($_SERVER['PHP_SELF']);

$__nav_items = [
    ['href' => 'index.php',        'match' => 'index.php',        'label' => 'Panel'],
    ['href' => 'musteriler.php',   'match' => 'musteriler.php',   'label' => 'Müşteriler'],
    ['href' => 'gunluk_giris.php', 'match' => 'gunluk_giris.php', 'label' => 'Günlük Giriş'],
    ['href' => 'taziye_ekle.php',  'match' => 'taziye_ekle.php',  'label' => 'Taziye Yemeği'],
    ['href' => 'calisanlar.php',   'match' => 'calisanlar.php',   'label' => 'Çalışanlar / Maaş'],
    ['href' => 'raporlama.php',    'match' => 'raporlama.php',    'label' => 'Raporlama'],
    ['href' => 'giderler.php',     'match' => 'giderler.php',     'label' => 'Giderler'],
];
?>
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bereket Sofram Yönetim</title>
<link rel="stylesheet" href="assets/app.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
</head>
<body class="bg-[#faf7f2] min-h-screen pb-24 md:pb-6">

<header class="sticky top-0 z-30 bg-white/90 backdrop-blur border-b border-slate-100">
    <div class="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
        <div class="flex items-center gap-2">
            <span class="text-2xl">🍽️</span>
            <span class="font-bold text-slate-800 text-lg">Bereket Sofram</span>
        </div>
        <a href="logout.php" title="Çıkış Yap"
           class="flex items-center gap-1.5 text-sm text-slate-500 hover:text-red-600 px-3 py-2 rounded-lg hover:bg-red-50 transition">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            <span class="hidden sm:inline">Çıkış</span>
        </a>
    </div>

    <!-- Masaüstünde görünen üst sekme menüsü -->
    <nav class="hidden md:block border-t border-slate-100">
        <div class="max-w-5xl mx-auto px-4 flex gap-1">
            <?php foreach ($__nav_items as $item): $aktif = $__mevcut_sayfa === $item['match']; ?>
                <a href="<?= $item['href'] ?>"
                   class="px-4 py-3 text-sm font-medium border-b-2 -mb-px transition
                          <?= $aktif ? 'border-amber-500 text-amber-700' : 'border-transparent text-slate-500 hover:text-slate-800' ?>">
                    <?= $item['label'] ?>
                </a>
            <?php endforeach; ?>
        </div>
    </nav>
</header>

<div class="max-w-5xl mx-auto px-4 py-6">
