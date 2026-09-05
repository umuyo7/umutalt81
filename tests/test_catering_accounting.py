import copy
import unittest
from decimal import Decimal as D

from app.catering_accounting import customer_balance, statement_preview, statement_confirmation, report, money
from app.catering_preflight import EXPECTED, validate


class CateringAccountingTests(unittest.TestCase):
    def setUp(self):
        self.customer = dict(id='1', faturali_mi='1', devreden_borc='100',
                             anlasilan_yemek_fiyati='999', mesai_yemek_fiyati='999')
        self.meals = [dict(id='1', musteri_id='1', tarih='2026-08-31', yemek_adedi='2',
                          mesai_yemek_adedi='0', gunluk_toplam_tutar='100', mesai_toplam_tutar='0'),
                      dict(id='2', musteri_id='1', tarih='2026-09-01', yemek_adedi='3',
                          mesai_yemek_adedi='1', gunluk_toplam_tutar='180', mesai_toplam_tutar='70')]
        self.payments = [dict(musteri_id='1', tarih='2026-08-31', tutar='50'),
                         dict(musteri_id='1', tarih='2026-09-01', tutar='100')]

    def test_historical_prices_and_vat(self):
        result = statement_preview(self.customer, self.meals, self.payments, '2026-09-01', '2026-09-30')
        self.assertEqual(result['normal_yemek_fiyati'], D('60'))
        self.assertEqual(result['onceki_bakiye'], D('160'))
        self.assertEqual(result['kdv_tutari'], D('25'))
        self.assertEqual(result['kalan_bakiye'], D('335'))

    def test_non_invoice(self):
        self.customer['faturali_mi'] = '0'
        self.assertEqual(customer_balance(self.customer, self.meals, self.payments)['balance'], D('300'))

    def test_advance_difference_and_repeat(self):
        preview = statement_preview(self.customer, self.meals, self.payments, '2026-09-01', '2026-09-30')
        self.assertEqual(statement_confirmation(preview, 160, 150)['new_payment_amount'], D('50'))
        self.payments.append(dict(musteri_id='1', tarih='2026-09-30', tutar='50'))
        repeat = statement_preview(self.customer, self.meals, self.payments, '2026-09-01', '2026-09-30')
        self.assertEqual(statement_confirmation(repeat, 160, 150)['new_payment_amount'], 0)
        self.assertEqual(statement_confirmation(repeat, 160, 10)['alinan_avans'], 150)

    def test_customer_credit_does_not_pay_others_debt(self):
        other = dict(self.customer, id='2', devreden_borc='0')
        payments = self.payments + [dict(musteri_id='2', tarih='2026-09-01', tutar='1000')]
        result = report([self.customer, other], self.meals, payments,
                        [dict(tarih='2026-09-01', toplam_tutar='500')],
                        [dict(tarih='2026-09-01', tutar='20')], '2026-09-01', '2026-09-30')
        self.assertEqual(result['receivables'], D('335'))
        self.assertEqual(result['revenue'], D('775'))
        self.assertEqual(result['net'], D('755'))

    def test_detail_vat_discrepancy_is_explicit(self):
        result = customer_balance(self.customer, self.meals, self.payments)
        self.assertEqual(result['balance'], D('335'))
        self.assertEqual(result['legacy_detail_balance'], D('300'))

    def test_invalid_money_and_period_fail(self):
        for value in ['NaN', 'Infinity', 'bad', None]:
            with self.assertRaises(ValueError):
                money(value)
        with self.assertRaises(ValueError):
            statement_preview(self.customer, self.meals, self.payments, '2026-09-30', '2026-09-01')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.data = {'format': 'bereket-catering-snapshot-v1', 'missing_tables': [],
                     'additional_tables': [], 'tables': {name: {'row_count': 0,
                     'columns': [{'Field': 'id', 'Type': 'int(11)'}], 'rows': [],
                     'totals': {'id': '0'}} for name in EXPECTED}}

    def test_empty_valid_and_no_mutation(self):
        before = copy.deepcopy(self.data)
        self.assertTrue(validate(self.data)['valid'])
        self.assertEqual(before, self.data)

    def test_corrupt_totals_detected(self):
        self.data['tables']['musteriler']['totals']['id'] = '1'
        self.assertFalse(validate(self.data)['valid'])

    def test_missing_table_not_silently_skipped(self):
        del self.data['tables']['ekstreler']
        self.assertFalse(validate(self.data)['valid'])

    def test_orphan_not_silently_skipped(self):
        t = self.data['tables']['tahsilatlar']
        t['columns'].append({'Field': 'musteri_id', 'Type': 'int(11)'})
        t.update(rows=[{'id': '1', 'musteri_id': '99'}], row_count=1, totals={'id': '1', 'musteri_id': '99'})
        self.assertFalse(validate(self.data)['valid'])

    def test_decimal_precision(self):
        t = self.data['tables']['musteriler']
        t['columns'].append({'Field': 'devreden_borc', 'Type': 'decimal(18,2)'})
        t.update(rows=[{'id': '1', 'devreden_borc': '9999999999999999.99'}], row_count=1,
                 totals={'id': '1', 'devreden_borc': '9999999999999999.99'})
        self.assertTrue(validate(self.data)['valid'])


if __name__ == '__main__':
    unittest.main()
