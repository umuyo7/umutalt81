<?php
/**
 * Ortak yardımcı fonksiyonlar
 */

// Sayıyı Türk Lirası formatında yazdırır: 1234.5 -> "1.234,50 ₺"
function format_para($tutar): string
{
    return number_format((float)$tutar, 2, ',', '.') . ' ₺';
}

// XSS koruması için kısa htmlspecialchars sarmalayıcı
function h($str): string
{
    return htmlspecialchars((string)($str ?? ''), ENT_QUOTES, 'UTF-8');
}

// Tarihi Y-m-d formatından d.m.Y formatına çevirir
function format_tarih(?string $tarih): string
{
    if (!$tarih) {
        return '-';
    }
    $ts = strtotime($tarih);
    return $ts ? date('d.m.Y', $ts) : '-';
}

// Girilen bir tarih dizesinin geçerli bir Y-m-d tarihi olup olmadığını kontrol eder
function gecerli_tarih_mi(?string $tarih): bool
{
    return (bool)($tarih && preg_match('/^\d{4}-\d{2}-\d{2}$/', $tarih) && strtotime($tarih));
}

// İki tarih arasındaki gün sayısını (her iki uç dahil) hesaplar
function gun_sayisi_hesapla(string $baslangic, string $bitis): int
{
    $b1 = new DateTime($baslangic);
    $b2 = new DateTime($bitis);
    if ($b2 < $b1) {
        return 0;
    }
    return $b1->diff($b2)->days + 1;
}
