<?php
/**
 * includes/EkstrePDF.php
 * Bereket Sofram kurumsal kimliğine (koyu yeşil + altın) uygun,
 * logo başlıklı, profesyonel görünümlü PDF ekstre/fatura şablonu.
 */

require_once __DIR__ . '/../vendor/tcpdf/tcpdf.php';

class EkstrePDF extends TCPDF
{
    // Kurumsal renkler (logodan alınmıştır)
    public const RENK_YESIL      = [9, 57, 33];    // #093921 koyu yeşil
    public const RENK_YESIL_ACIK = [235, 241, 236]; // açık yeşil zemin
    public const RENK_ALTIN      = [201, 154, 58];  // #C99A3A altın
    public const RENK_GRI        = [110, 110, 110];
    public const RENK_KOYU       = [40, 40, 40];

    public string $belgeBasligi = 'CARİ HESAP EKSTRESİ';
    public string $ekstreNo = '';
    public string $ekstreTarihi = '';

    public function Header()
    {
        // Kurumsal logo ve iletişim bilgileri
        // Kare logo, orijinal oranı korunarak ve kırpılmadan yerleştirilir.
        $logoGenislik = 40;
        $logoYukseklik = 40;
        // Ana dosya yüklenmemiş eski kurulumlarda mevcut logo ile devam edilir.
        $logoDosyalari = [FIRMA_LOGO, __DIR__ . '/../assets/logo-header.jpg', __DIR__ . '/../assets/logo.png'];
        foreach ($logoDosyalari as $logoDosyasi) {
            if (file_exists($logoDosyasi)) {
                $this->Image($logoDosyasi, 10, 4, $logoGenislik, $logoYukseklik);
                break;
            }
        }

        $this->SetXY(56, 7);
        $this->SetFont('dejavusans', 'B', 13);
        $this->SetTextColor(...self::RENK_YESIL);
        $this->Cell(134, 7, FIRMA_ADI, 0, 1, 'L');

        $this->SetX(56);
        $this->SetFont('dejavusans', '', 8.2);
        $this->SetTextColor(...self::RENK_GRI);
        $this->Cell(134, 4.5, FIRMA_ADRES, 0, 1, 'L');
        $this->SetX(56);
        $this->Cell(134, 4.5, 'Tel: ' . FIRMA_TELEFON . '  ·  ' . FIRMA_YETKILI . ': ' . FIRMA_YETKILI_TELEFON, 0, 1, 'L');

        // Başlığın altına ince altın çizgi
        $altCizgiY = 48;
        $this->SetLineStyle(['width' => 0.8, 'color' => self::RENK_ALTIN]);
        $this->Line(10, $altCizgiY, $this->getPageWidth() - 10, $altCizgiY);

        // Belge başlığı şeridi
        $y = $altCizgiY + 4;
        $this->SetXY(10, $y);
        $this->SetFont('dejavusans', 'B', 13);
        $this->SetTextColor(...self::RENK_YESIL);
        $this->Cell(120, 8, mb_strtoupper($this->belgeBasligi), 0, 0, 'L');

        $this->SetFont('dejavusans', '', 9);
        $this->SetTextColor(...self::RENK_GRI);
        $this->SetXY(-90, $y + 1);
        $this->Cell(80, 5, 'Ekstre No: ' . $this->ekstreNo, 0, 2, 'R');
        $this->SetX(-90);
        $this->Cell(80, 5, 'Tarih: ' . $this->ekstreTarihi, 0, 2, 'R');

        $this->SetY($y + 11);
    }

    public function Footer()
    {
        $this->SetY(-20);
        $this->SetLineStyle(['width' => 0.5, 'color' => self::RENK_ALTIN]);
        $this->Line(10, $this->GetY(), $this->getPageWidth() - 10, $this->GetY());

        $this->SetY(-17);
        $this->SetFont('dejavusans', '', 8);
        $this->SetTextColor(...self::RENK_GRI);
        $adres = FIRMA_ADRES . '  ·  Tel: ' . FIRMA_TELEFON . '  ·  ' . FIRMA_YETKILI . ': ' . FIRMA_YETKILI_TELEFON;
        $this->MultiCell(0, 4, $adres, 0, 'C');
        $this->SetY(-9);
        $this->SetFont('dejavusans', '', 8);
        $this->Cell(0, 4, 'Sayfa ' . $this->getAliasNumPage() . ' / ' . $this->getAliasNbPages(), 0, 0, 'C');
    }

    /** Bölüm başlığı (altın zeminli şerit) çizer */
    public function bolumBasligi(string $baslik): void
    {
        $this->SetFillColor(...self::RENK_YESIL);
        $this->SetTextColor(255, 255, 255);
        $this->SetFont('dejavusans', 'B', 10.5);
        $this->Cell(0, 8, '  ' . mb_strtoupper($baslik), 0, 1, 'L', true);
        $this->Ln(1.5);
        $this->SetTextColor(...self::RENK_KOYU);
    }

    /** Etiket : değer satırı (bilgi tablosu için) */
    public function bilgiSatiri(string $etiket, string $deger, float $genislikEtiket = 55): void
    {
        $this->SetFont('dejavusans', 'B', 9.5);
        $this->SetTextColor(...self::RENK_GRI);
        $this->Cell($genislikEtiket, 6.5, $etiket, 0, 0, 'L');
        $this->SetFont('dejavusans', '', 9.5);
        $this->SetTextColor(...self::RENK_KOYU);
        $this->Cell(0, 6.5, $deger, 0, 1, 'L');
    }
}
