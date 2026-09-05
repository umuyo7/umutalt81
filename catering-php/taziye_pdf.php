<?php
/** Tek seferlik taziye yemeği için kurumsal PDF çıktısı. */
require_once 'config.php';
require_once 'includes/auth.php';
require_once 'includes/functions.php';
require_once 'includes/EkstrePDF.php';

$id = (int)($_GET['id'] ?? 0);
$stmt = $pdo->prepare('SELECT * FROM taziye_yemekleri WHERE id = ?');
$stmt->execute([$id]);
$kayit = $stmt->fetch();
if (!$kayit) {
    die('Taziye yemeği kaydı bulunamadı.');
}

$pdf = new EkstrePDF('P', 'mm', 'A4', true, 'UTF-8', false);
$pdf->belgeBasligi = 'TAZİYE YEMEĞİ ÖZETİ';
$pdf->ekstreNo = 'TAZ-' . str_pad((string)$kayit['id'], 5, '0', STR_PAD_LEFT);
$pdf->ekstreTarihi = date('d.m.Y');
$pdf->SetCreator('Bereket Sofram Yönetim');
$pdf->SetAuthor(FIRMA_ADI);
$pdf->SetTitle('Taziye Yemeği - ' . $kayit['firma_adi']);
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
$pdf->RoundedRect(10, $kutuY, 190, 20, 2, '1111', 'DF');
$pdf->SetXY(14, $kutuY + 3);
$pdf->SetFont('dejavusans', 'B', 12);
$pdf->SetTextColor(...$yesil);
$pdf->Cell(0, 7, $kayit['firma_adi'], 0, 1, 'L');
$pdf->SetX(14);
$pdf->SetFont('dejavusans', '', 9);
$pdf->SetTextColor(...$gri);
$pdf->Cell(0, 5, 'Taziye yemeği tarihi: ' . format_tarih($kayit['tarih']), 0, 1, 'L');
$pdf->SetY($kutuY + 24);

$pdf->bolumBasligi('Yemek Detayı');
$pdf->SetFont('dejavusans', 'B', 9);
$pdf->SetFillColor(...$yesil);
$pdf->SetTextColor(255, 255, 255);
$pdf->Cell(85, 7, '  Açıklama', 0, 0, 'L', true);
$pdf->Cell(30, 7, 'Adet', 0, 0, 'C', true);
$pdf->Cell(35, 7, 'Birim Fiyat', 0, 0, 'C', true);
$pdf->Cell(40, 7, 'Toplam', 0, 1, 'C', true);

$pdf->SetFont('dejavusans', '', 9.5);
$pdf->SetTextColor(...$koyu);
$pdf->SetFillColor(247, 244, 236);
$pdf->Cell(85, 8, '  Taziye Yemeği', 0, 0, 'L', true);
$pdf->Cell(30, 8, number_format((int)$kayit['adet'], 0, ',', '.'), 0, 0, 'C', true);
$pdf->Cell(35, 8, format_para($kayit['birim_fiyat']), 0, 0, 'C', true);
$pdf->Cell(40, 8, format_para($kayit['toplam_tutar']), 0, 1, 'C', true);

if ($kayit['aciklama']) {
    $pdf->Ln(8);
    $pdf->bolumBasligi('Açıklama');
    $pdf->SetFont('dejavusans', '', 9.5);
    $pdf->SetTextColor(...$koyu);
    $pdf->MultiCell(0, 6, $kayit['aciklama'], 0, 'L');
}

$pdf->Ln(18);
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

$dosyaAdi = 'taziye_yemegi_' . preg_replace('/[^A-Za-z0-9_-]/', '_', $kayit['firma_adi']) . '_' . $kayit['id'] . '.pdf';
$pdf->Output($dosyaAdi, 'I');
