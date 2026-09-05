<?php
/** Günlük girişlerin gün gün gösterildiği, özet ekstreden bağımsız detay PDF'i. */
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';
require_once 'includes/EkstrePDF.php';

$id = (int)($_GET['id'] ?? 0);
$stmt = $pdo->prepare("
    SELECT e.*, m.sirket_ismi, m.sahis_adi, m.telefon, m.adres
    FROM ekstreler e
    JOIN musteriler m ON m.id = e.musteri_id
    WHERE e.id = ?
");
$stmt->execute([$id]);
$e = $stmt->fetch();
if (!$e) {
    die('Ekstre bulunamadı.');
}

$stmt = $pdo->prepare("
    SELECT tarih, yemek_adedi, mesai_yemek_adedi,
           gunluk_toplam_tutar, mesai_toplam_tutar
    FROM gunluk_yemek_verileri
    WHERE musteri_id = ? AND tarih BETWEEN ? AND ?
    ORDER BY tarih ASC
");
$stmt->execute([$e['musteri_id'], $e['baslama_tarihi'], $e['bitis_tarihi']]);
$gunlukDetaylar = $stmt->fetchAll();

$pdf = new EkstrePDF('P', 'mm', 'A4', true, 'UTF-8', false);
$pdf->belgeBasligi = 'GÜN GÜN YEMEK DETAYI';
$pdf->ekstreNo = 'EKS-' . str_pad((string)$e['id'], 5, '0', STR_PAD_LEFT);
$pdf->ekstreTarihi = date('d.m.Y');
$pdf->SetCreator('Bereket Sofram Catering Yönetim Sistemi');
$pdf->SetAuthor(FIRMA_ADI);
$pdf->SetTitle('Günlük Detay - ' . $e['sirket_ismi']);
$pdf->setPrintHeader(true);
$pdf->setPrintFooter(true);
$pdf->SetMargins(10, 75, 10);
$pdf->SetHeaderMargin(0);
$pdf->SetFooterMargin(12);
$pdf->SetAutoPageBreak(true, 24);
$pdf->AddPage();

$yesil = EkstrePDF::RENK_YESIL;
$altin = EkstrePDF::RENK_ALTIN;
$koyu = EkstrePDF::RENK_KOYU;
$gri = EkstrePDF::RENK_GRI;

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
$yetkili = trim(($e['sahis_adi'] ?: '') . ($e['telefon'] ? '  ·  Tel: ' . $e['telefon'] : ''));
$pdf->Cell(0, 5, $yetkili ?: '-', 0, 2, 'L');
$pdf->SetY($kutuY + $musteriKutuYukseklik + 4);

$pdf->bolumBasligi('Dönem');
$pdf->SetFont('dejavusans', '', 9.5);
$pdf->SetTextColor(...$koyu);
$pdf->Cell(55, 6.5, 'Başlama Tarihi', 0, 0, 'L');
$pdf->Cell(45, 6.5, format_tarih($e['baslama_tarihi']), 0, 0, 'L');
$pdf->Cell(35, 6.5, 'Bitiş Tarihi', 0, 0, 'L');
$pdf->Cell(55, 6.5, format_tarih($e['bitis_tarihi']), 0, 1, 'L');
$pdf->Ln(3);

$pdf->bolumBasligi('Günlük Yemek Girişleri');
$tabloBasligi = function () use ($pdf, $yesil): void {
    $pdf->SetFont('dejavusans', 'B', 8.7);
    $pdf->SetFillColor(...$yesil);
    $pdf->SetTextColor(255, 255, 255);
    $pdf->Cell(45, 7, '  Tarih', 0, 0, 'L', true);
    $pdf->Cell(40, 7, 'Yemek Adedi', 0, 0, 'C', true);
    $pdf->Cell(40, 7, 'Mesai Adet', 0, 0, 'C', true);
    $pdf->Cell(65, 7, 'Günlük Tutar', 0, 1, 'C', true);
};
$tabloBasligi();

$normalToplam = 0;
$mesaiToplam = 0;
$tutarToplam = 0.0;
$satirBg = false;
foreach ($gunlukDetaylar as $gun) {
    if ($pdf->GetY() + 7 > $pdf->getPageHeight() - 24) {
        $pdf->AddPage();
        $pdf->bolumBasligi('Günlük Yemek Girişleri (Devam)');
        $tabloBasligi();
    }
    $gunlukTutar = (float)$gun['gunluk_toplam_tutar'] + (float)$gun['mesai_toplam_tutar'];
    $normalToplam += (int)$gun['yemek_adedi'];
    $mesaiToplam += (int)$gun['mesai_yemek_adedi'];
    $tutarToplam += $gunlukTutar;
    $pdf->SetFont('dejavusans', '', 9);
    $pdf->SetTextColor(...$koyu);
    $pdf->SetFillColor(247, 244, 236);
    $pdf->Cell(45, 7, '  ' . format_tarih($gun['tarih']), 0, 0, 'L', $satirBg);
    $pdf->Cell(40, 7, number_format((int)$gun['yemek_adedi'], 0, ',', '.'), 0, 0, 'C', $satirBg);
    $pdf->Cell(40, 7, number_format((int)$gun['mesai_yemek_adedi'], 0, ',', '.'), 0, 0, 'C', $satirBg);
    $pdf->Cell(65, 7, format_para($gunlukTutar), 0, 1, 'C', $satirBg);
    $satirBg = !$satirBg;
}

if (!$gunlukDetaylar) {
    $pdf->SetFont('dejavusans', '', 9.5);
    $pdf->SetTextColor(...$gri);
    $pdf->Cell(0, 8, 'Bu dönem için günlük yemek girişi bulunmuyor.', 0, 1, 'C');
} else {
    $pdf->SetFont('dejavusans', 'B', 9.2);
    $pdf->SetFillColor(...$altin);
    $pdf->SetTextColor(255, 255, 255);
    $pdf->Cell(45, 7.5, '  TOPLAM', 0, 0, 'L', true);
    $pdf->Cell(40, 7.5, number_format($normalToplam, 0, ',', '.'), 0, 0, 'C', true);
    $pdf->Cell(40, 7.5, number_format($mesaiToplam, 0, ',', '.'), 0, 0, 'C', true);
    $pdf->Cell(65, 7.5, format_para($tutarToplam), 0, 1, 'C', true);
}

$kayitliAraToplam = array_key_exists('donem_ara_toplami', $e) ? (float)$e['donem_ara_toplami'] : 0.0;
$araToplam = abs($kayitliAraToplam) < 0.005 && abs($tutarToplam) >= 0.005
    ? $tutarToplam
    : $kayitliAraToplam;
$kdvOrani = array_key_exists('kdv_orani', $e) ? (float)$e['kdv_orani'] : 0.0;
$kdvTutari = array_key_exists('kdv_tutari', $e) ? (float)$e['kdv_tutari'] : 0.0;
if ($kdvOrani > 0) {
    $pdf->Ln(5);
    $pdf->SetX(110);
    $pdf->SetFont('dejavusans', '', 9.5);
    $pdf->SetTextColor(...$koyu);
    $pdf->Cell(55, 7, 'Dönem Ara Toplamı', 0, 0, 'L');
    $pdf->Cell(35, 7, format_para($araToplam), 0, 1, 'R');
    $pdf->SetX(110);
    $pdf->Cell(55, 7, 'KDV (%' . number_format($kdvOrani, 0, ',', '.') . ')', 0, 0, 'L');
    $pdf->Cell(35, 7, format_para($kdvTutari), 0, 1, 'R');
    $pdf->SetX(110);
    $pdf->SetFillColor(...$yesil);
    $pdf->SetTextColor(255, 255, 255);
    $pdf->SetFont('dejavusans', 'B', 9.5);
    $pdf->Cell(55, 8, '  KDV DÂHİL TOPLAM', 0, 0, 'L', true);
    $pdf->Cell(35, 8, format_para($e['donem_toplami']) . '  ', 0, 1, 'R', true);
}

$dosyaAdi = 'gunluk_detay_' . preg_replace('/[^A-Za-z0-9_-]/', '_', $e['sirket_ismi']) . '_' . $e['id'] . '.pdf';
$pdf->Output($dosyaAdi, 'I');
