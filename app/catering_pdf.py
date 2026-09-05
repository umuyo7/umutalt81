"""Catering'in üç PDF çıktısı; mevcut kayıtlı ekstre tutarları korunur."""
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from .catering_accounting import money, rounded, ZERO

GREEN = colors.HexColor('#093921')
GOLD = colors.HexColor('#c99a3a')
ADDRESS = 'Göztepe Mh. Kazım Karabekir Cd. No:13/A Bağcılar / İSTANBUL'
CONTACT = 'Tel: 0 (212) 447 20 02 · Mesut ALTUNDAĞ: 0 (534) 846 45 83'


def fmt(value):
    return f'{rounded(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' ₺'


def dt(value):
    return str(value)[8:10] + '.' + str(value)[5:7] + '.' + str(value)[:4]


class PageCountCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = []

    def showPage(self):
        self.saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        count = len(self.saved)
        for state in self.saved:
            self.__dict__.update(state)
            self.setFont('CateringFont', 8)
            self.setFillColor(colors.grey)
            self.drawCentredString(A4[0]/2, 9*mm, f'Sayfa {self._pageNumber} / {count}')
            super().showPage()
        super().save()


def build_pdf(store, kind, ident):
    regular = os.getenv('CATERING_PDF_FONT', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    bold = os.getenv('CATERING_PDF_BOLD_FONT', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    if not Path(regular).is_file():
        for candidate, bold_candidate in (
            ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
            ('/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf', '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'),
        ):
            if Path(candidate).is_file():
                regular, bold = candidate, bold_candidate
                break
    if not Path(regular).is_file():
        raise ValueError('PDF Türkçe fontu bulunamadı.')
    if not Path(bold).is_file():
        bold = regular
    if 'CateringFont' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CateringFont', regular))
        pdfmetrics.registerFont(TTFont('CateringBold', bold))
    condolence = kind == 'taziye_pdf'
    detail = kind == 'ekstre_detay_pdf'
    record = store.get('taziye_yemekleri' if condolence else 'ekstreler', ident)
    customer = None if condolence else store.get('musteriler', record['musteri_id'])
    title = 'TAZİYE YEMEĞİ ÖZETİ' if condolence else 'GÜN GÜN YEMEK DETAYI' if detail else 'ÖZET CARİ HESAP EKSTRESİ'
    number = ('TAZ-' if condolence else 'EKS-') + str(ident).zfill(5)
    name = record['firma_adi'] if condolence else customer['sirket_ismi']
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=10*mm, rightMargin=10*mm,
                            topMargin=75*mm, bottomMargin=24*mm, title=number + ' - ' + name,
                            author='BS Bereket Sofram')
    style = ParagraphStyle('catering', fontName='CateringFont', fontSize=9, leading=13, textColor=colors.HexColor('#282828'))
    strong = ParagraphStyle('strong', parent=style, fontName='CateringBold', textColor=GREEN, fontSize=11, leading=15)
    heading = ParagraphStyle('heading', parent=strong, textColor=colors.white, backColor=GREEN, borderPadding=6, spaceBefore=10, spaceAfter=10)
    def p(value, s=style):
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), s)
    def table(rows, widths, header=True):
        formatted = [[p(cell) for cell in row] for row in rows]
        if header:
            head = ParagraphStyle('tablehead', parent=style, textColor=colors.white, fontName='CateringBold')
            formatted[0] = [p(cell, head) for cell in rows[0]]
        t = Table(formatted, colWidths=[n*mm for n in widths], repeatRows=1 if header else 0, hAlign='LEFT')
        commands = [('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),
                    ('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#e4e6df'))]
        if header:
            commands += [('BACKGROUND',(0,0),(-1,0),GREEN),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7f4ec')])]
        t.setStyle(TableStyle(commands))
        return t
    def decorate(canvas, document):
        canvas.saveState()
        w,h = A4
        logo = Path(__file__).parent / 'static' / 'firma_logo.png'
        if logo.exists():
            canvas.drawImage(str(logo),10*mm,h-44*mm,width=40*mm,height=40*mm,preserveAspectRatio=True,mask='auto')
        canvas.setFillColor(GREEN); canvas.setFont('CateringBold',13)
        canvas.drawString(56*mm,h-14*mm,'BS Bereket Sofram')
        canvas.setFillColor(colors.grey); canvas.setFont('CateringFont',8)
        canvas.drawString(56*mm,h-21*mm,ADDRESS)
        canvas.drawString(56*mm,h-27*mm,CONTACT)
        canvas.setStrokeColor(GOLD); canvas.setLineWidth(.8*mm)
        canvas.line(10*mm,h-48*mm,w-10*mm,h-48*mm)
        canvas.setFillColor(GREEN); canvas.setFont('CateringBold',11)
        canvas.drawString(10*mm,h-59*mm,title)
        canvas.setFillColor(colors.grey); canvas.setFont('CateringFont',8)
        canvas.drawRightString(w-10*mm,h-65*mm,number + ' · ' + datetime.now(ZoneInfo('Europe/Istanbul')).strftime('%d.%m.%Y'))
        canvas.setStrokeColor(GOLD); canvas.setLineWidth(.4*mm)
        canvas.line(10*mm,20*mm,w-10*mm,20*mm)
        canvas.setFont('CateringFont',7)
        canvas.drawCentredString(w/2,16*mm,ADDRESS)
        canvas.drawCentredString(w/2,12.5*mm,CONTACT)
        canvas.restoreState()
    flow = [p(name,strong),Spacer(1,3*mm)]
    if condolence:
        flow += [p('Taziye yemeği tarihi: ' + dt(record['tarih'])),p('Yemek Detayı',heading),
                 table([['Açıklama','Adet','Birim fiyat','Toplam'],['Taziye Yemeği',record['adet'],fmt(record['birim_fiyat']),fmt(record['toplam_tutar'])]], [85,30,35,40])]
        if record.get('aciklama'):
            flow += [p('Açıklama',heading),p(record['aciklama'])]
    else:
        flow += [p((customer.get('sahis_adi') or '') + ' · ' + (customer.get('telefon') or '')),
                 p('Dönem Bilgileri',heading),p(dt(record['baslama_tarihi']) + ' - ' + dt(record['bitis_tarihi']))]
        subtotal = money(record.get('donem_ara_toplami') or 0)
        if detail:
            meals = sorted([r for r in store.rows('gunluk_yemek_verileri',musteri_id=record['musteri_id'])
                            if str(record['baslama_tarihi']) <= str(r['tarih']) <= str(record['bitis_tarihi'])],key=lambda r:str(r['tarih']))
            rows = [['Tarih','Yemek adedi','Mesai adet','Günlük tutar']]
            for r in meals:
                rows.append([dt(r['tarih']),r['yemek_adedi'],r['mesai_yemek_adedi'],fmt(money(r['gunluk_toplam_tutar'])+money(r['mesai_toplam_tutar']))])
            calculated = sum((money(r['gunluk_toplam_tutar'])+money(r['mesai_toplam_tutar']) for r in meals),ZERO)
            if meals:
                rows.append(['TOPLAM',sum(r['yemek_adedi'] for r in meals),sum(r['mesai_yemek_adedi'] for r in meals),fmt(calculated)])
            else:
                rows.append(['Bu dönem için günlük yemek girişi bulunmuyor.','','',''])
            flow += [p('Günlük Yemek Girişleri',heading),table(rows,[45,40,40,65])]
            if abs(subtotal)<money('.005') and abs(calculated)>=money('.005'):
                subtotal = calculated
            if money(record.get('kdv_orani') or 0)>0:
                flow += [Spacer(1,5*mm),table([['Dönem ara toplamı',fmt(subtotal)],
                         [f"KDV (%{record['kdv_orani']})",fmt(record['kdv_tutari'])],
                         ['KDV dahil toplam',fmt(record['donem_toplami'])]],[130,60],False)]
        else:
            rows = [['Açıklama','Adet','Birim fiyat','Tutar'],['Yemek',record['normal_yemek_adedi'],fmt(record['normal_yemek_fiyati']),fmt(record['normal_yemek_tutari'])]]
            if money(record['mesai_yemek_adedi'])>0 or money(record['mesai_yemek_tutari'])>0:
                rows.append(['Mesai Yemeği',record['mesai_yemek_adedi'],fmt(record['mesai_yemek_fiyati']),fmt(record['mesai_yemek_tutari'])])
            calculated = money(record['normal_yemek_tutari'])+money(record['mesai_yemek_tutari'])+money(record.get('fazla_yemek_tutari') or 0)
            if abs(subtotal)<money('.005') and abs(calculated)>=money('.005'):
                subtotal = calculated
            rows.append(['ARA TOPLAM',int(record['normal_yemek_adedi'])+int(record['mesai_yemek_adedi']),'',fmt(subtotal)])
            summary = [['Önceki bakiye',fmt(record['onceki_bakiye'])],['Dönem ara toplamı (+)',fmt(subtotal)]]
            if money(record.get('kdv_orani') or 0)>0:
                summary.append([f"KDV (%{record['kdv_orani']}) (+)",fmt(record['kdv_tutari'])])
            summary += [['Alınan avans (-)',fmt(record['alinan_avans'])],['KALAN TOPLAM BAKİYE',fmt(record['kalan_bakiye'])]]
            flow += [p('Yemek Detayı',heading),table(rows,[90,30,35,35]),p('Cari Hesap Özeti',heading),table(summary,[130,60],False)]
    if not detail:
        flow.append(KeepTogether([Spacer(1,12*mm),table([['Teslim Eden','Teslim Alan / Onaylayan'],['_____________________','_____________________']],[95,95],False)]))
    doc.build(flow,onFirstPage=decorate,onLaterPages=decorate,canvasmaker=PageCountCanvas)
    return Response(buffer.getvalue(),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="{kind}_{ident}.pdf"'})
