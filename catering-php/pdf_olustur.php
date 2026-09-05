<?php
// Eski makbuz ekranı yerine tek ekstre akışı kullanılır.
// Bu yönlendirme, eski yer imleri olan kullanıcıların da güncel ekrana ulaşmasını sağlar.
require_once 'config.php';
require_once 'includes/auth.php';

$musteri_id = (int)($_GET['id'] ?? $_POST['id'] ?? 0);
header('Location: ekstre_olustur.php?musteri_id=' . $musteri_id);
exit;
