<?php
declare(strict_types=1);

// Bu dosyayı eski InfinityFree sitesinin ANA DİZİNİNE koyun.
// Yönetici girişi yapılmadan veri vermez. İndirme bittikten sonra silin.
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/includes/auth.php';

$allowedTables = [
    'musteriler',
    'gunluk_yemek_verileri',
    'tahsilatlar',
    'taziye_yemekleri',
    'gunluk_giderler',
    'calisanlar',
    'maas_odemeleri',
    'ekstreler',
];

$present = [];
$result = $pdo->query('SHOW TABLES');
foreach ($result->fetchAll(PDO::FETCH_NUM) as $row) {
    $present[(string) $row[0]] = true;
}

$tables = [];
foreach ($allowedTables as $table) {
    if (!isset($present[$table])) {
        $tables[$table] = [];
        continue;
    }
    // Tablo adı yalnız yukarıdaki sabit beyaz listeden gelir.
    $tables[$table] = $pdo->query("SELECT * FROM `{$table}` ORDER BY `id`")->fetchAll(PDO::FETCH_ASSOC);
}

$payload = [
    'format' => 'bereket-infinityfree-v1',
    'exported_at' => gmdate('c'),
    'tables' => $tables,
];

$json = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR);
$filename = 'bereket-infinityfree-' . gmdate('Ymd-His') . '.json';
header('Content-Type: application/json; charset=utf-8');
header('Content-Disposition: attachment; filename="' . $filename . '"');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');
echo $json;
