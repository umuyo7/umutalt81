<?php
/**
 * Dönem Hesap Makbuzu - PDF üretimi (tFPDF ile, logolu, profesyonel tasarım)
 */

require_once __DIR__ . '/../lib/tfpdf/font/unifont/ttfonts.php';
require_once __DIR__ . '/../lib/tfpdf/tfpdf.php';

class MakbuzPDF extends tFPDF
{
    public $logoPath;

    function Header()
    {
        if ($this->page > 1) {
            // Devam sayfalarında daha ince bir logo şeridi
            $w = $this->GetPageWidth();
            $h = $w * 166 / 597 * 0.55;
            $this->Image($this->logoPath, 0, 0, $w, $h);
            $this->SetY($h + 6);
        }
    }

    function Footer()
    {
        $this->SetY(-14);
        $this->SetFont('DejaVu', '', 8);
        $this->SetTextColor(150, 150, 150);
        $this->Cell(0, 8, 'Sayfa ' . $this->PageNo() . ' / {nb}', 0, 0, 'C');
    }

    function GetBreakTrigger()
    {
        return $this->PageBreakTrigger;
    }
}

function pdf_para($tutar): string
{
    return number_format((float)$tutar, 2, ',', '.') . ' ₺';
}

/**
 * $d beklenen anahtarlar:
 *  sirket_ismi, sahis_adi, telefon, adres,
 *  baslangic_tarihi, bitis_tarihi, gun_sayisi, kisi_sayisi,
 *  normal_adet, normal_fiyat, normal_tutar,
 *  mesai_adet, mesai_fiyat, mesai_tutar,
 *  taziye_adet, taziye_tutar, taziyeler (liste),
 *  fazla_yemek_adedi,
 *  genel_toplam_adet, donem_toplam_tutar,
 *  onceki_bakiye, alinan_avans, kalan_toplam_bakiye,
 *  gunler (opsiyonel günlük döküm listesi)
 */
function pdf_makbuz_olustur(array $d): string
{
    $pdf = new MakbuzPDF('P', 'mm', 'A4');
    $pdf->logoPath = __DIR__ . '/../assets/logo.png';
    $pdf->AliasNbPages();
    $pdf->SetAutoPageBreak(true, 20);
    $pdf->SetMargins(15, 15, 15);

    $pdf->AddFont('DejaVu', '', 'DejaVuSans.ttf', true);
    $pdf->AddFont('DejaVu', 'B', 'DejaVuSans-Bold.ttf', true);

    $pdf->AddPage();

    // ---- Tam genişlik logo banner (ilk sayfa) ----
    $pageW = $pdf->GetPageWidth();
    $bannerH = $pageW * 166 / 597;
    $pdf->Image($pdf->logoPath, 0, 0, $pageW, $bannerH);
    $pdf->SetY($bannerH + 8);

    // ---- Başlık ----
    $pdf->SetFont('DejaVu', 'B', 16);
    $pdf->SetTextColor(15, 61, 38);
    $pdf->Cell(0, 8, 'DÖNEM HESAP MAKBUZU', 0, 1, 'L');

    $pdf->SetFont('DejaVu', '', 9);
    $pdf->SetTextColor(120, 120, 120);
    $pdf->Cell(0, 6, 'Makbuz Tarihi: ' . $d['makbuz_tarihi'], 0, 1, 'L');
    $pdf->Ln(4);

    // ---- Bilgi tablosu (ss1 formatı: etiket : değer) ----
    $labelW = 62;
    $valueW = $pageW - 15 - 15 - $labelW;
    $rowH = 8;

    $satirlar = [
        ['FİRMA ADI', $d['sirket_ismi']],
    ];
    if (!empty($d['sahis_adi'])) {
        $satirlar[] = ['YETKİLİ', $d['sahis_adi']];
    }
    $satirlar[] = ['BAŞLAMA TARİHİ', $d['baslangic_tarihi']];
    $satirlar[] = ['BİTİŞ TARİHİ', $d['bitis_tarihi']];
    $satirlar[] = ['GÜN SAYISI', $d['gun_sayisi'] . ' gün'];
    $satirlar[] = ['KİŞİ SAYISI', $d['kisi_sayisi'] !== null && $d['kisi_sayisi'] !== '' ? $d['kisi_sayisi'] . ' kişi' : '-'];
    $satirlar[] = ['FAZLA YEMEK ADEDİ', $d['fazla_yemek_adedi'] > 0 ? $d['fazla_yemek_adedi'] . ' adet' : '-'];
    $satirlar[] = ['NORMAL YEMEK', $d['normal_adet'] . ' adet  x  ' . pdf_para($d['normal_fiyat']) . '  =  ' . pdf_para($d['normal_tutar'])];
    if ($d['mesai_adet'] > 0) {
        $satirlar[] = ['MESAİ YEMEĞİ', $d['mesai_adet'] . ' adet  x  ' . pdf_para($d['mesai_fiyat']) . '  =  ' . pdf_para($d['mesai_tutar'])];
    }
    if ($d['taziye_adet'] > 0) {
        $satirlar[] = ['TAZİYE YEMEĞİ', $d['taziye_adet'] . ' adet  =  ' . pdf_para($d['taziye_tutar'])];
    }
    $satirlar[] = ['GENEL TOPLAM (ADET)', $d['genel_toplam_adet'] . ' yemek'];
    $satirlar[] = ['BU DÖNEM TOPLAM TUTAR', pdf_para($d['donem_toplam_tutar'])];
    $satirlar[] = ['ÖNCEKİ BAKİYE', pdf_para($d['onceki_bakiye'])];
    $satirlar[] = ['ALINAN AVANS', pdf_para($d['alinan_avans'])];

    $pdf->SetLineWidth(0.2);
    $pdf->SetDrawColor(200, 200, 200);
    $pdf->SetFont('DejaVu', 'B', 10);

    foreach ($satirlar as $i => $s) {
        $x = $pdf->GetX();
        $y = $pdf->GetY();
        $pdf->SetFillColor($i % 2 === 0 ? 250 : 255, $i % 2 === 0 ? 248 : 255, $i % 2 === 0 ? 242 : 255);
        $pdf->SetFont('DejaVu', 'B', 9.5);
        $pdf->SetTextColor(90, 70, 20);
        $pdf->Cell($labelW, $rowH, '  ' . $s[0], 1, 0, 'L', true);
        $pdf->SetFont('DejaVu', '', 10);
        $pdf->SetTextColor(40, 40, 40);
        $pdf->Cell($valueW, $rowH, '  ' . $s[1], 1, 1, 'L', true);
    }

    // ---- Kalan Toplam Bakiye (vurgulu satır) ----
    $pdf->SetFont('DejaVu', 'B', 11);
    $pdf->SetFillColor(15, 61, 38);
    $pdf->SetTextColor(255, 255, 255);
    $pdf->Cell($labelW, 10, '  KALAN TOPLAM BAKİYE', 1, 0, 'L', true);
    $pdf->Cell($valueW, 10, '  ' . pdf_para($d['kalan_toplam_bakiye']), 1, 1, 'L', true);

    $pdf->Ln(3);
    $pdf->SetFont('DejaVu', '', 7.5);
    $pdf->SetTextColor(140, 140, 140);
    $pdf->MultiCell(0, 4, 'Hesaplama: Kalan Toplam Bakiye = Önceki Bakiye + Bu Dönem Toplam Tutar - Alınan Avans', 0, 'L');

    // ---- Taziye yemekleri detayı (varsa) ----
    if (!empty($d['taziyeler'])) {
        $pdf->Ln(5);
        $pdf->SetFont('DejaVu', 'B', 11);
        $pdf->SetTextColor(15, 61, 38);
        $pdf->Cell(0, 7, 'Taziye Yemeği Detayı', 0, 1, 'L');

        $w1 = 28; $w2 = 78; $w3 = 22; $w4 = 30; $w5 = $pageW - 15 - 15 - $w1 - $w2 - $w3 - $w4;

        $draw_taziye_header = function () use ($pdf, $w1, $w2, $w3, $w4, $w5) {
            $pdf->SetFont('DejaVu', 'B', 9);
            $pdf->SetFillColor(15, 61, 38);
            $pdf->SetTextColor(255, 255, 255);
            $pdf->Cell($w1, 7, 'Tarih', 1, 0, 'C', true);
            $pdf->Cell($w2, 7, 'Açıklama', 1, 0, 'L', true);
            $pdf->Cell($w3, 7, 'Adet', 1, 0, 'C', true);
            $pdf->Cell($w4, 7, 'B.Fiyat', 1, 0, 'C', true);
            $pdf->Cell($w5, 7, 'Tutar', 1, 1, 'C', true);
        };

        $draw_taziye_header();

        $pdf->SetFont('DejaVu', '', 9);
        $pdf->SetTextColor(40, 40, 40);
        $i = 0;
        foreach ($d['taziyeler'] as $t) {
            if ($pdf->GetY() + 6.5 > $pdf->GetBreakTrigger()) {
                $pdf->AddPage();
                $draw_taziye_header();
                $pdf->SetFont('DejaVu', '', 9);
                $pdf->SetTextColor(40, 40, 40);
            }
            $pdf->SetFillColor($i % 2 === 0 ? 250 : 255, $i % 2 === 0 ? 248 : 255, $i % 2 === 0 ? 242 : 255);
            $pdf->Cell($w1, 6.5, $t['tarih'], 1, 0, 'C', true);
            $pdf->Cell($w2, 6.5, $t['aciklama'], 1, 0, 'L', true);
            $pdf->Cell($w3, 6.5, (string)$t['adet'], 1, 0, 'C', true);
            $pdf->Cell($w4, 6.5, pdf_para($t['birim_fiyat']), 1, 0, 'C', true);
            $pdf->Cell($w5, 6.5, pdf_para($t['tutar']), 1, 1, 'C', true);
            $i++;
        }
    }

    // ---- Günlük döküm (varsa) ----
    if (!empty($d['gunler'])) {
        $pdf->Ln(5);
        $pdf->SetFont('DejaVu', 'B', 11);
        $pdf->SetTextColor(15, 61, 38);
        $pdf->Cell(0, 7, 'Günlük Yemek Dökümü', 0, 1, 'L');

        $gw1 = 30; $gw2 = 35; $gw3 = 35; $gw4 = $pageW - 15 - 15 - $gw1 - $gw2 - $gw3;

        $draw_gunler_header = function () use ($pdf, $gw1, $gw2, $gw3, $gw4) {
            $pdf->SetFont('DejaVu', 'B', 9);
            $pdf->SetFillColor(15, 61, 38);
            $pdf->SetTextColor(255, 255, 255);
            $pdf->Cell($gw1, 7, 'Tarih', 1, 0, 'C', true);
            $pdf->Cell($gw2, 7, 'Normal Adet', 1, 0, 'C', true);
            $pdf->Cell($gw3, 7, 'Mesai Adet', 1, 0, 'C', true);
            $pdf->Cell($gw4, 7, 'Günlük Tutar', 1, 1, 'C', true);
        };

        $draw_gunler_header();

        $pdf->SetFont('DejaVu', '', 9);
        $pdf->SetTextColor(40, 40, 40);
        $i = 0;
        foreach ($d['gunler'] as $g) {
            if ($pdf->GetY() + 6.5 > $pdf->GetBreakTrigger()) {
                $pdf->AddPage();
                $draw_gunler_header();
                $pdf->SetFont('DejaVu', '', 9);
                $pdf->SetTextColor(40, 40, 40);
            }
            $pdf->SetFillColor($i % 2 === 0 ? 250 : 255, $i % 2 === 0 ? 248 : 255, $i % 2 === 0 ? 242 : 255);
            $pdf->Cell($gw1, 6.5, $g['tarih'], 1, 0, 'C', true);
            $pdf->Cell($gw2, 6.5, (string)$g['yemek_adedi'], 1, 0, 'C', true);
            $pdf->Cell($gw3, 6.5, (string)$g['mesai_adedi'], 1, 0, 'C', true);
            $pdf->Cell($gw4, 6.5, pdf_para($g['gunluk_toplam_tutar'] + $g['mesai_toplam_tutar']), 1, 1, 'C', true);
            $i++;
        }
    }

    return $pdf->Output('S'); // string olarak döndür
}
