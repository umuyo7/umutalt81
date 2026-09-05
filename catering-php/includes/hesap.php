<?php
/**
 * Dönem / bakiye hesaplama yardımcı fonksiyonları.
 * musteri_detay.php ve pdf_olustur.php tarafından ortak kullanılır.
 */

// Belirli bir tarihten ÖNCEKİ tüm hizmet ve ödemelerden bakiye hesaplar.
// (yemek + mesai + taziye toplamı) - (tahsilatlar toplamı)
function hesap_onceki_bakiye(PDO $pdo, int $musteri_id, string $baslangic_tarihi): float
{
    $stmt = $pdo->prepare("
        SELECT COALESCE(SUM(gunluk_toplam_tutar + mesai_toplam_tutar), 0)
        FROM gunluk_yemek_verileri
        WHERE musteri_id = ? AND tarih < ?
    ");
    $stmt->execute([$musteri_id, $baslangic_tarihi]);
    $yemek_toplam = (float)$stmt->fetchColumn();

    $stmt = $pdo->prepare("
        SELECT COALESCE(SUM(tutar), 0) FROM taziye_yemekleri
        WHERE musteri_id = ? AND tarih < ?
    ");
    $stmt->execute([$musteri_id, $baslangic_tarihi]);
    $taziye_toplam = (float)$stmt->fetchColumn();

    $stmt = $pdo->prepare("
        SELECT COALESCE(SUM(tutar), 0) FROM tahsilatlar
        WHERE musteri_id = ? AND tarih < ?
    ");
    $stmt->execute([$musteri_id, $baslangic_tarihi]);
    $odeme_toplam = (float)$stmt->fetchColumn();

    return ($yemek_toplam + $taziye_toplam) - $odeme_toplam;
}

// Belirli bir tarih aralığı (dahil) için dönem verilerini hesaplar.
function hesap_donem_verileri(PDO $pdo, int $musteri_id, string $baslangic, string $bitis): array
{
    // Normal + mesai yemek günlük kayıtları
    $stmt = $pdo->prepare("
        SELECT tarih, yemek_adedi, gunluk_toplam_tutar,
               mesai_yemek_adedi AS mesai_adedi, mesai_toplam_tutar
        FROM gunluk_yemek_verileri
        WHERE musteri_id = ? AND tarih BETWEEN ? AND ?
        ORDER BY tarih ASC
    ");
    $stmt->execute([$musteri_id, $baslangic, $bitis]);
    $gunler = $stmt->fetchAll();

    $gun_sayisi         = count($gunler);
    $normal_adet_toplam = 0;
    $normal_tutar_toplam = 0.0;
    $mesai_adet_toplam  = 0;
    $mesai_tutar_toplam = 0.0;

    foreach ($gunler as $g) {
        $normal_adet_toplam  += (int)$g['yemek_adedi'];
        $normal_tutar_toplam += (float)$g['gunluk_toplam_tutar'];
        $mesai_adet_toplam   += (int)$g['mesai_adedi'];
        $mesai_tutar_toplam  += (float)$g['mesai_toplam_tutar'];
    }

    // Taziye yemekleri (dönem içinde)
    $stmt = $pdo->prepare("
        SELECT tarih, aciklama, adet, birim_fiyat, tutar
        FROM taziye_yemekleri
        WHERE musteri_id = ? AND tarih BETWEEN ? AND ?
        ORDER BY tarih ASC
    ");
    $stmt->execute([$musteri_id, $baslangic, $bitis]);
    $taziyeler = $stmt->fetchAll();

    $taziye_adet_toplam  = 0;
    $taziye_tutar_toplam = 0.0;
    foreach ($taziyeler as $t) {
        $taziye_adet_toplam  += (int)$t['adet'];
        $taziye_tutar_toplam += (float)$t['tutar'];
    }

    // Dönem içindeki ödemeler (Alınan Avans alanını öntanımlı doldurmak için)
    $stmt = $pdo->prepare("
        SELECT COALESCE(SUM(tutar), 0) FROM tahsilatlar
        WHERE musteri_id = ? AND tarih BETWEEN ? AND ?
    ");
    $stmt->execute([$musteri_id, $baslangic, $bitis]);
    $odeme_toplam = (float)$stmt->fetchColumn();

    $genel_yemek_adedi = $normal_adet_toplam + $mesai_adet_toplam + $taziye_adet_toplam;
    $donem_toplam_tutar = $normal_tutar_toplam + $mesai_tutar_toplam + $taziye_tutar_toplam;

    return [
        'gun_sayisi'           => $gun_sayisi,
        'gunler'               => $gunler,
        'normal_adet_toplam'   => $normal_adet_toplam,
        'normal_tutar_toplam'  => $normal_tutar_toplam,
        'mesai_adet_toplam'    => $mesai_adet_toplam,
        'mesai_tutar_toplam'   => $mesai_tutar_toplam,
        'taziyeler'            => $taziyeler,
        'taziye_adet_toplam'   => $taziye_adet_toplam,
        'taziye_tutar_toplam'  => $taziye_tutar_toplam,
        'genel_yemek_adedi'    => $genel_yemek_adedi,
        'donem_toplam_tutar'   => $donem_toplam_tutar,
        'donem_odeme_toplam'   => $odeme_toplam,
    ];
}
