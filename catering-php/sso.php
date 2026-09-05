<?php
declare(strict_types=1);
require_once __DIR__ . '/config.php';

if (session_status() === PHP_SESSION_NONE) {
    session_start();
}

$timestamp = filter_input(INPUT_GET, 'ts', FILTER_VALIDATE_INT);
$signature = (string) ($_GET['sig'] ?? '');
$now = time();
$payload = 'catering:' . $timestamp;
$expected = hash_hmac('sha256', $payload, CATERING_SSO_SECRET);

if (!$timestamp || abs($now - $timestamp) > 60 || !hash_equals($expected, $signature)) {
    http_response_code(403);
    exit('Geçersiz veya süresi dolmuş giriş bağlantısı.');
}

session_regenerate_id(true);
$_SESSION['giris_yapildi'] = true;
$_SESSION['sso_timestamp'] = $timestamp;
header('Location: index.php');
exit;
