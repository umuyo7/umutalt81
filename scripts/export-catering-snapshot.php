<?php
declare(strict_types=1);
// Yalnız CLI. Web üzerinden müşteri/veritabanı dökümü yayınlanamaz.
if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}
ini_set('display_errors', '0');
$pdo = null;
try {
    $host = getenv('CATERING_DB_HOST');
    $name = getenv('CATERING_DB_NAME');
    $user = getenv('CATERING_DB_USER');
    $password = getenv('CATERING_DB_PASSWORD');
    if (!$host || !$name || !$user || !$password) {
        throw new RuntimeException('Ortam ayarları eksik');
    }
    $pdo = new PDO("mysql:host=$host;dbname=$name;charset=utf8mb4", $user, $password, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_STRINGIFY_FETCHES => true,
    ]);
    // Şema değişikliği yapılmayan bir zaman diliminde çalıştırılmalı.
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
    $pdo->exec('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY');
    $expected = ['musteriler', 'gunluk_yemek_verileri', 'taziye_yemekleri',
        'tahsilatlar', 'gunluk_giderler', 'calisanlar', 'maas_odemeleri', 'ekstreler'];
    $list = $pdo->query("SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME")->fetchAll();
    $found = array_column($list, 'TABLE_NAME');
    $export = ['format' => 'bereket-catering-snapshot-v1', 'exported_at' => gmdate('c'),
        'missing_tables' => array_values(array_diff($expected, $found)),
        'additional_tables' => array_values(array_diff($found, $expected)), 'tables' => []];
    foreach ($list as $entry) {
        $table = $entry['TABLE_NAME'];
        if (!in_array($table, $expected, true)) {
            continue; // Bilinmeyen tablolardan kimlik bilgisi çıkarmıyoruz.
        }
        if (strtolower((string)$entry['ENGINE']) !== 'innodb') {
            throw new RuntimeException('Transaction desteklemeyen kaynak tablo');
        }
        $columns = $pdo->query("SHOW FULL COLUMNS FROM `$table`")->fetchAll();
        $ddl = $pdo->query("SHOW CREATE TABLE `$table`")->fetch();
        $rows = $pdo->query("SELECT * FROM `$table` ORDER BY id")->fetchAll();
        $totals = [];
        foreach ($columns as $column) {
            if (preg_match('/^(decimal|numeric|int|bigint|smallint|tinyint|mediumint)\b/i', $column['Type'])) {
                $field = str_replace('`', '``', $column['Field']);
                $totals[$column['Field']] = (string)$pdo->query("SELECT COALESCE(SUM(`$field`), 0) FROM `$table`")->fetchColumn();
            }
        }
        $export['tables'][$table] = ['columns' => $columns, 'create_sql' => $ddl['Create Table'],
            'row_count' => count($rows), 'totals' => $totals, 'rows' => $rows];
    }
    $json = json_encode($export, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    $pdo->exec('COMMIT');
    fwrite(STDOUT, $json . PHP_EOL);
} catch (Throwable $error) {
    if ($pdo !== null && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    // Bağlantı parolası/DSN ve veriler hata çıktısına yazılmaz.
    fwrite(STDERR, "Catering dışa aktarımı tamamlanamadı. JSON dosyasını kullanmayın.\n");
    exit(1);
}
