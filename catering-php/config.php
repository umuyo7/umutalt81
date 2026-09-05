<?php
declare(strict_types=1);

error_reporting(E_ALL);
ini_set('display_errors', getenv('APP_DEBUG') === 'true' ? '1' : '0');
date_default_timezone_set('Europe/Istanbul');

define('DB_HOST', getenv('CATERING_DB_HOST') ?: 'catering_db');
define('DB_NAME', getenv('CATERING_DB_NAME') ?: 'bereket_catering');
define('DB_USER', getenv('CATERING_DB_USER') ?: 'bereket_user');
define('DB_PASS', getenv('CATERING_DB_PASSWORD') ?: '');
$panelPrefix = getenv('APP_PREFIX');
define('PANEL_PREFIX', rtrim($panelPrefix === false ? '/xyz' : $panelPrefix, '/'));
unset($panelPrefix);
define('CATERING_SSO_SECRET', getenv('CATERING_SSO_SECRET') ?: '');

$sessionDir = __DIR__ . '/includes/session_data';
if (!is_dir($sessionDir)) {
    mkdir($sessionDir, 0700, true);
}
ini_set('session.save_path', $sessionDir);
ini_set('session.use_strict_mode', '1');
ini_set('session.cookie_httponly', '1');
ini_set('session.cookie_samesite', 'Lax');
ini_set('session.cookie_secure', getenv('COOKIE_HTTPS_ONLY') === 'true' ? '1' : '0');
unset($sessionDir);

define('FIRMA_ADI', 'BS Bereket Sofram');
define('FIRMA_ADRES', 'Göztepe Mh. Kazım Karabekir Cd. No:13/A Bağcılar / İSTANBUL');
define('FIRMA_TELEFON', '0 (212) 447 20 02');
define('FIRMA_YETKILI', 'Mesut ALTUNDAĞ');
define('FIRMA_YETKILI_TELEFON', '0 (534) 846 45 83');
define('FIRMA_LOGO', __DIR__ . '/assets/logo.png');

if (DB_PASS === '' || strlen(CATERING_SSO_SECRET) < 32) {
    http_response_code(500);
    exit('Catering ortam ayarları eksik.');
}

try {
    $pdo = new PDO(
        'mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4',
        DB_USER,
        DB_PASS,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]
    );
} catch (PDOException $exception) {
    error_log('Catering DB connection failed: ' . $exception->getMessage());
    http_response_code(503);
    exit('Veritabanına şu anda bağlanılamıyor.');
}
