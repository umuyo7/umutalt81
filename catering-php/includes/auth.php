<?php
/**
 * includes/auth.php
 * Bu dosya, korumalı her sayfanın en başında (config.php'den hemen sonra)
 * çağrılmalıdır. Giriş yapılmamışsa kullanıcıyı login.php'ye yönlendirir.
 */

if (session_status() === PHP_SESSION_NONE) {
    session_start();
}

if (empty($_SESSION['giris_yapildi'])) {
    header('Location: ' . PANEL_PREFIX . '/login');
    exit;
}
