<?php
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';
require_once 'includes/EkstrePDF.php';

$id = (int)($_GET['id'] ?? 0);

$stmt = $pdo->prepare("
    SELECT e.*, m.sirket_ismi, m.sahis_adi, m.telefon, m.eposta, m.adres
    FROM ekstreler e
    JOIN musteriler m ON m.id = e.musteri_id
    WHERE e.id = ?
");
$stmt->execute([$id]);
$e = $stmt->fetch();

if (!$e) {
    die('Ekstre bulunamadı.');
}

$pdf = new EkstrePDF('P', 'mm', 'A4', true, 'UTF-8', false);
$pdf->belgeBasligi = 'ÖZET CARİ HESAP EKSTRESİ';
$pdf->ekstreNo = 'EKS-' . str_pad((string)$e['id'], 5, '0', STR_PAD_LEFT);
$pdf->ekstreTarihi = date('d.m.Y');

$pdf->SetCreator('Bereket Sofram Catering Yönetim Sistemi');
$pdf->SetAuthor(FIRMA_ADI);
$pdf->SetTitle($pdf->ekstreNo . ' - ' . $e['sirket_ismi']);
$pdf->setPrintHeader(true);
$pdf->setPrintFooter(true);
$pdf->SetMargins(10, 75, 10);
$pdf->SetHeaderMargin(0);
$pdf->SetFooterMargin(12);
$pdf->SetAutoPageBreak(true, 24);
$pdf->AddPage();

$yesil = EkstrePDF::RENK_YESIL;
$altin = EkstrePDF::RENK_ALTIN;
$koyu  = EkstrePDF::RENK_KOYU;
$gri   = EkstrePDF::RENK_GRI;

// ---------------------------------------------------------------
// Müşteri bilgi kutusu
// ---------------------------------------------------------------
$pdf->SetFillColor(...EkstrePDF::RENK_YESIL_ACIK);
$pdf->SetDrawColor(...$altin);
$pdf->SetLineWidth(0.3);
$kutuY = $pdf->GetY();
$musteriKutuYukseklik = 20;
$pdf->RoundedRect(10, $kutuY, 190, $musteriKutuYukseklik, 2, '1111', 'DF');

$pdf->SetXY(14, $kutuY + 2.5);
$pdf->SetFont('dejavusans', 'B', 11.5);
$pdf->SetTextColor(...$yesil);
$pdf->Cell(0, 6, $e['sirket_ismi'], 0, 2, 'L');

$pdf->SetX(14);
$pdf->SetFont('dejavusans', '', 9);
$pdf->SetTextColor(...$gri);
$yetkili_satiri = trim(($e['sahis_adi'] ?: '') . ($e['telefon'] ? '  ·  Tel: ' . $e['telefon'] : ''));
$pdf->Cell(0, 5, $yetkili_satiri ?: '-', 0, 2, 'L');

$pdf->SetY($kutuY + $musteriKutuYukseklik + 4);

// ---------------------------------------------------------------
// Özet PDF'de yalnızca dönem tarihleri yer alır.
// ---------------------------------------------------------------
$pdf->bolumBasligi('Dönem Bilgileri');

$solX = 12;
$sagX = 110;
$satirY = $pdf->GetY();

$pdf->SetXY($solX, $satirY);
$pdf->bilgiSatiri('Başlama Tarihi', format_tarih($e['baslama_tarihi']));
$pdf->SetXY($solX, $pdf->GetY());
$pdf->bilgiSatiri('Bitiş Tarihi', format_tarih($e['bitis_tarihi']));

$pdf->Ln(2);

// ---------------------------------------------------------------
// Yemek detay tablosu
// ---------------------------------------------------------------
$pdf->bolumBasligi('Yemek Detayı');

$basliklar = ['Açıklama', 'Adet', 'Birim Fiyat', 'Tutar'];
$genislikler = [90, 30, 35, 35];

$pdf->SetFont('dejavusans', 'B', 9);
$pdf->SetFillColor(...$yesil);
$pdf->SetTextColor(255, 255, 255);
foreach ($basliklar as $i => $baslik) {
    $align = $i === 0 ? 'L' : 'C';
    $pdf->Cell($genislikler[$i], 7, ($i === 0 ? '  ' : '') . $baslik, 0, 0, $align, true);
}
$pdf->Ln();

$satirlar = [];
$satirlar[] = ['Yemek', (int)$e['normal_yemek_adedi'], (float)$e['normal_yemek_fiyati'], (float)$e['normal_yemek_tutari']];
if ((float)$e['mesai_yemek_adedi'] > 0 || (float)$e['mesai_yemek_tutari'] > 0) {
    $satirlar[] = ['Mesai Yemeği', (int)$e['mesai_yemek_adedi'], (float)$e['mesai_yemek_fiyati'], (float)$e['mesai_yemek_tutari']];
}
$toplamAdet = (int)$e['normal_yemek_adedi'] + (int)$e['mesai_yemek_adedi'];
$hesaplananAraToplam = (float)$e['normal_yemek_tutari'] + (float)$e['mesai_yemek_tutari'] + (float)$e['fazla_yemek_tutari'];
$kayitliAraToplam = array_key_exists('donem_ara_toplami', $e) ? (float)$e['donem_ara_toplami'] : 0.0;
$araToplam = abs($kayitliAraToplam) < 0.005 && abs($hesaplananAraToplam) >= 0.005
    ? $hesaplananAraToplam
    : $kayitliAraToplam;
$kdvOrani = array_key_exists('kdv_orani', $e) ? (float)$e['kdv_orani'] : 0.0;
$kdvTutari = array_key_exists('kdv_tutari', $e) ? (float)$e['kdv_tutari'] : 0.0;

$pdf->SetFont('dejavusans', '', 9.5);
$pdf->SetTextColor(...$koyu);
$satirBg = false;
foreach ($satirlar as $s) {
    $pdf->SetFillColor(247, 244, 236);
    $pdf->Cell($genislikler[0], 7, '  ' . $s[0], 0, 0, 'L', $satirBg);
    $pdf->Cell($genislikler[1], 7, number_format($s[1], 0, ',', '.'), 0, 0, 'C', $satirBg);
    $pdf->Cell($genislikler[2], 7, format_para($s[2]), 0, 0, 'C', $satirBg);
    $pdf->Cell($genislikler[3], 7, format_para($s[3]), 0, 0, 'C', $satirBg);
    $pdf->Ln();
    $satirBg = !$satirBg;
}

// Toplam satırı
$pdf->SetFont('dejavusans', 'B', 9.5);
$pdf->SetFillColor(...$altin);
$pdf->SetTextColor(255, 255, 255);
$pdf->Cell($genislikler[0], 7.5, '  ARA TOPLAM (' . $toplamAdet . ' adet yemek)', 0, 0, 'L', true);
$pdf->Cell($genislikler[1] + $genislikler[2], 7.5, '', 0, 0, 'C', true);
$pdf->Cell($genislikler[3], 7.5, format_para($araToplam), 0, 0, 'C', true);
$pdf->Ln(10);

// ---------------------------------------------------------------
// Cari hesap özeti
// ---------------------------------------------------------------
$pdf->bolumBasligi('Cari Hesap Özeti');

$ozetX = 110;
$ozetGenislik = 90;
$pdf->SetX($ozetX);

$pdf->SetFont('dejavusans', '', 10);
$pdf->SetTextColor(...$koyu);

$ozetSatirlari = [
    ['Önceki Bakiye', (float)$e['onceki_bakiye'], false],
    ['Dönem Ara Toplamı (+)', $araToplam, false],
    ['Alınan Avans (-)', (float)$e['alinan_avans'], false],
];

if ($kdvOrani > 0) {
    array_splice($ozetSatirlari, 2, 0, [['KDV (%' . number_format($kdvOrani, 0, ',', '.') . ') (+)', $kdvTutari, false]]);
}

foreach ($ozetSatirlari as $satir) {
    $pdf->SetX($ozetX);
    $pdf->SetFont('dejavusans', '', 10);
    $pdf->Cell($ozetGenislik * 0.62, 7.5, $satir[0], 0, 0, 'L');
    $pdf->Cell($ozetGenislik * 0.38, 7.5, format_para($satir[1]), 0, 0, 'R');
    $pdf->Ln();
}

$pdf->SetX($ozetX);
$pdf->SetLineStyle(['width' => 0.3, 'color' => $gri]);
$pdf->Line($ozetX, $pdf->GetY() + 1, $ozetX + $ozetGenislik, $pdf->GetY() + 1);
$pdf->Ln(3);

$pdf->SetX($ozetX);
$pdf->SetFillColor(...$yesil);
$pdf->SetTextColor(255, 255, 255);
$pdf->SetFont('dejavusans', 'B', 10);
$pdf->Cell($ozetGenislik * 0.62, 9, '  KALAN TOPLAM BAKİYE', 0, 0, 'L', true);
$pdf->Cell($ozetGenislik * 0.38, 9, format_para($e['kalan_bakiye']) . '  ', 0, 0, 'R', true);
$pdf->Ln(16);

// ---------------------------------------------------------------
// İmza alanı
// ---------------------------------------------------------------
$pdf->SetFont('dejavusans', '', 9.5);
$pdf->SetTextColor(...$koyu);
$pdf->SetX(12);
$pdf->Cell(85, 6, 'Teslim Eden', 0, 0, 'C');
$pdf->Cell(20, 6, '', 0, 0, 'C');
$pdf->Cell(85, 6, 'Teslim Alan / Onaylayan', 0, 1, 'C');

$pdf->SetX(12);
$pdf->Cell(85, 0, '', 'T', 0, 'C');
$pdf->Cell(20, 0, '', 0, 0, 'C');
$pdf->Cell(85, 0, '', 'T', 1, 'C');

$dosyaAdi = 'ekstre_' . preg_replace('/[^A-Za-z0-9_-]/', '_', $e['sirket_ismi']) . '_' . $e['id'] . '.pdf';
$pdf->Output($dosyaAdi, 'I');
