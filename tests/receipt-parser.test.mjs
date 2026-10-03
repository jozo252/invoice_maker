import test from 'node:test';
import assert from 'node:assert/strict';
import {parseMoney, validDate, extractReceipt} from '../static/crm/receipt-parser.mjs';

test('cents are exact for supported Slovak formats', () => {
  for (const [value, cents] of [['0,01',1],['12.5',1250],['1 234,56',123456],['1\u00a0234,56',123456],['10000000',1000000000]]) {
    assert.equal(parseMoney(value), cents, value);
  }
  for (const value of ['',null,'1.234,56','1,234.56','12 34,56','12,345','-1,00','1e3','NaN','10000000,01']) {
    assert.equal(parseMoney(value), null, String(value));
  }
});

test('invalid dates never become normalized calendar dates', () => {
  assert.equal(validDate('2024-02-29'), true);
  for (const value of ['2026-02-29','2026-02-30','2026-13-01','16.09.2026','2026-9-16']) assert.equal(validDate(value), false, value);
});

test('reads labelled EUR total, date and vendor', () => {
  const receipt = extractReceipt('Stavebniny Poprad\nPokladničný doklad\n16.09.2026 11:23\nZÁKLAD 100,00\nDPH CELKOM 23,45\nCELKOM 123,45 EUR\nHOTOVOSŤ 150,00\nVÝDAVOK 26,55');
  assert.equal(receipt.amountCents,12345);
  assert.equal(receipt.date,'2026-09-16');
  assert.equal(receipt.vendor,'Stavebniny Poprad');
});

test('supports a total printed on the following line', () => {
  assert.equal(extractReceipt('Predajňa Náradie\nK ÚHRADE\n1 234,56 EUR').amountCents,123456);
});

test('repeated identical totals are safe but conflicting totals need manual entry', () => {
  assert.equal(extractReceipt('SPOLU 12,50\nCELKOM 12,50 EUR').amountCents,1250);
  const conflicting = extractReceipt('SPOLU 12,50\nCELKOM 15,50 EUR');
  assert.equal(conflicting.amountCents,null);
  assert.match(conflicting.reason,/rozdielne/);
});

test('tax, change, cash and subtotal labels cannot authorize a total', () => {
  for (const text of ['DPH CELKOM 10,50','SUBTOTAL 12,50','MEDZISÚČET SPOLU 12,50','VÝDAVOK CELKOM 12,50','HOTOVOSŤ CELKOM 12,50','CASH TOTAL 12,50']) {
    assert.equal(extractReceipt(text).amountCents,null,text);
  }
  assert.equal(extractReceipt('CELKOM S DPH 25,50 EUR').amountCents,2550);
});

test('foreign currency, refunds, OCR corruption and zero require manual review', () => {
  for (const text of ['TOTAL 123,45 USD','CELKOM 100,00 CZK','TOTAL $12.50','CELKOM -12,50 EUR','CELKOM 12,5O EUR','CELKOM 0,00 EUR','CELKOM 12,50 KS']) {
    assert.equal(extractReceipt(text).amountCents,null,text);
  }
  assert.equal(extractReceipt('CELKOM 25,50 EUR\nTOTAL 25,50 USD').amountCents,null);
});

test('unlabelled prices and impossible dates stay empty', () => {
  const receipt=extractReceipt('Predajňa\n30.02.2026\nKábel 125,00 EUR\nCena 25,00');
  assert.equal(receipt.amountCents,null);
  assert.equal(receipt.date,'');
});

test('due and delivery dates cannot become the receipt or invoice issue date', () => {
  for (const text of [
    'Pokyny ku platbe\nDátum splatnosti\n29.7.2026\nČiastka\n108,00',
    'Dátum splatnosti29.7.2026',
    'Dátum splatnosti 29.7.2026',
    'Due date:29.07.2026',
    'DUE DATE\n29.07.2026',
    'Dátum dodania29.7.2026',
    'Dátum dodania 29.7.2026',
  ]) assert.equal(extractReceipt(text).date, '', text);
  const invoice=extractReceipt('Dodávateľ\nDátum splatnosti 29.7.2026\nDátum dodania 20.7.2026\nDátum vystavenia 21.7.2026\nCELKOM 108,00 EUR');
  assert.equal(invoice.date,'2026-07-21');
  assert.equal(invoice.amountCents,10800);
});

test('browser OCR requires visible EUR beside the total before proposing an EUR cost', () => {
  assert.equal(extractReceipt('CELKOM 18,40').amountCents,1840);
  assert.equal(extractReceipt('CELKOM 18,40').currency,null);
  for (const text of ['CELKOM 18,40 EUR','CELKOM 18,40 €','K ÚHRADE EUR\n18,40','SPOLU 18,40\nCELKOM 18,40 EUR']) {
    assert.equal(extractReceipt(text).currency,'EUR',text);
  }
  assert.equal(extractReceipt('PLATBA EUR\nCELKOM 18,40').currency,null);
  assert.equal(extractReceipt('CELKOM 18,40 EUR\nCELKOM 20,00 EUR').currency,null);
  assert.equal(extractReceipt('CELKOM 18,40 CZK').currency,null);
});
