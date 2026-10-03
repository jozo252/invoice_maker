"""AI receipt suggestions: disposable data and mocked provider, never paid calls."""
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.error
import uuid

from extensions import db
from models import Job, JobReceipt, User
from crm import ai_receipts as ai
from tests import test_crm_pilot as pilot_fixture


DUMMY_KEY = 'sk-synthetic-only-test-key-not-a-real-credential-72f441b59f'
RESULT = {
    'vendor': 'TEST Elektro', 'receipt_date': '2026-09-16', 'amount': '18.40',
    'detected_amount': '18.40', 'currency': 'EUR', 'document_type': 'receipt',
    'source': 'openai', 'message': 'Synthetic proposal; check the original.',
}
RAW_RESULT = {
    'vendor': 'TEST Elektro', 'receipt_date': '2026-09-16', 'amount': '18.40',
    'currency': 'EUR', 'document_type': 'receipt',
}


class AiRouteTests(unittest.TestCase):
    def setUp(self):
        # Avoid even reading server environment credentials while creating fixtures.
        self.key_patch = patch('crm_pilot.api_key', return_value=DUMMY_KEY)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.network = patch('crm.ai_receipts.urllib.request.build_opener',
                             side_effect=AssertionError('Network calls prohibited in unit tests'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.fixture = pilot_fixture.PilotTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.app = self.fixture.app
        self.app.config['CRM_OPENAI_API_KEY'] = DUMMY_KEY
        self.assertEqual(self.fixture.login().status_code, 302)
        self.job_id, image = self.fixture.receipt_fixture()
        with patch('crm.receipts.shutil.disk_usage', return_value=Mock(free=1024 ** 3)):
            response = self.fixture.upload(self.job_id, image)
        self.assertEqual(response.status_code, 302)
        self.receipt_id = response.headers['Location'].rsplit('/', 1)[1]
        self.state = Path(self.app.config['CRM_AI_STATE_PATH'])

    def extract(self, payload=None, receipt_id=None, csrf=True, headers=None, data=None):
        request_headers = {'Content-Type': 'application/json'}
        if csrf:
            request_headers['X-CSRFToken'] = self.fixture.csrf('/crm/clients')
        request_headers.update(headers or {})
        return self.fixture.request(
            f'/crm/receipts/{receipt_id or self.receipt_id}/extract', method='POST',
            data=data if data is not None else json.dumps({'revision': 0} if payload is None else payload),
            headers=request_headers,
        )

    def receipt(self):
        with self.app.app_context():
            row = db.session.get(JobReceipt, self.receipt_id)
            return {column.name: getattr(row, column.name) for column in JobReceipt.__table__.columns}

    def attempts(self):
        if not self.state.exists():
            return []
        with closing(sqlite3.connect(self.state)) as connection:
            return list(connection.execute('SELECT status FROM attempts ORDER BY id'))

    def confirmed_cost(self):
        path = self.app.config['SQLALCHEMY_DATABASE_URI'].removeprefix('sqlite:///')
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute(
                "SELECT coalesce(SUM(amount_cents),0) FROM job_receipts WHERE job_id=? AND status='confirmed'",
                (self.job_id,),
            ).fetchone()[0]

    def test_auth_owner_csrf_origin_reject_before_provider(self):
        with patch('crm.ai_receipts.call_provider') as provider:
            self.assertEqual(self.extract(csrf=False).status_code, 400)
            self.assertEqual(self.extract(headers={'Origin': 'https://foreign.example'}).status_code, 403)
            with self.app.app_context():
                user = User(email='foreign@example.invalid', username='foreign_ai', password_hash='unused')
                db.session.add(user)
                db.session.flush()
                now = datetime.now(timezone.utc)
                job = Job(user_id=user.id, title='Foreign AI job', status='new', created_at=now, updated_at=now)
                db.session.add(job)
                db.session.flush()
                foreign_id = str(uuid.uuid4())
                db.session.add(JobReceipt(
                    id=foreign_id, user_id=user.id, job_id=job.id, sha256='b' * 64,
                    object_name=f'{user.id}/' + 'b' * 64, original_name='foreign.png', mime='image/png',
                ))
                db.session.commit()
            self.assertEqual(self.extract(receipt_id=foreign_id).status_code, 404)
            self.fixture.browser = self.app.test_client()
            self.assertEqual(self.extract(csrf=False).status_code, 401)
            provider.assert_not_called()
        self.assertEqual(self.attempts(), [])

    def test_invalid_json_and_revision_reject_before_provider(self):
        with patch('crm.ai_receipts.call_provider') as provider:
            for revision in (None, True, False, -1, '0', 0.0, [], {}):
                with self.subTest(revision=revision):
                    self.assertEqual(self.extract({'revision': revision}).status_code, 400)
            self.assertEqual(self.extract({}).status_code, 400)
            self.assertEqual(self.extract(data='not json').status_code, 400)
            self.assertEqual(self.extract(data='[]').status_code, 400)
            self.assertEqual(self.extract({'revision': 1}).status_code, 409)
            provider.assert_not_called()
        self.assertEqual(self.attempts(), [])

    def confirm_during_provider(self, *args, **kwargs):
        # A separate SQLite connection emulates confirmation by another request.
        with closing(sqlite3.connect(self.app.config['SQLALCHEMY_DATABASE_URI'].removeprefix('sqlite:///'))) as connection:
            connection.execute(
                "UPDATE job_receipts SET status='confirmed',revision=revision+1,vendor=?,receipt_date=?,"
                'amount_cents=?,confirmed_at=? WHERE id=?',
                ('Manually corrected vendor', '2026-09-17', 1940, '2026-09-17 12:00:00', self.receipt_id),
            )
            connection.commit()
        return dict(RESULT)

    def test_confirmed_receipt_is_not_sent_again(self):
        self.confirm_during_provider()
        before = self.receipt()
        with patch('crm.ai_receipts.call_provider') as provider:
            response = self.extract({'revision': 1})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(self.extract({'revision': 1, 'manual': False}).status_code, 409)
            provider.assert_not_called()
        self.assertEqual(self.receipt(), before)
        self.assertEqual(self.attempts(), [])

    def test_manual_reread_requires_actual_boolean_and_current_revision(self):
        self.confirm_during_provider()
        before = self.receipt()
        with patch('crm.ai_receipts.call_provider') as provider:
            for manual in (None, 0, 1, 'true', 'false', '', [], {}):
                with self.subTest(manual=manual):
                    response = self.extract({'revision': 1, 'manual': manual})
                    self.assertEqual(response.status_code, 400)
            self.assertEqual(self.extract({'revision': 0, 'manual': True}).status_code, 409)
            provider.assert_not_called()
        self.assertEqual(self.receipt(), before)
        self.assertEqual(self.confirmed_cost(), 1940)
        self.assertEqual(self.attempts(), [])

    def test_manual_reread_of_confirmed_receipt_returns_only_proposal_without_changing_cost(self):
        self.confirm_during_provider()
        before = self.receipt()
        with patch('crm.ai_receipts.call_provider', return_value=dict(RESULT)) as provider:
            response = self.extract({'revision': 1, 'manual': True})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()['amount'], '18.40')
            self.assertFalse(response.get_json()['cached'])
            cached = self.extract({'revision': 1, 'manual': True})
            self.assertEqual(cached.status_code, 200)
            self.assertTrue(cached.get_json()['cached'])
            # A cached suggestion still cannot trigger an automatic reread.
            self.assertEqual(self.extract({'revision': 1}).status_code, 409)
            self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.receipt(), before)
        self.assertEqual(self.confirmed_cost(), 1940)
        self.assertEqual(self.attempts(), [('success',)])

    def test_confirmed_manual_reread_rejects_revision_changed_during_provider(self):
        self.confirm_during_provider()
        with patch('crm.ai_receipts.call_provider', side_effect=self.confirm_during_provider) as provider:
            response = self.extract({'revision': 1, 'manual': True})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(provider.call_count, 1)
        row = self.receipt()
        self.assertEqual((row['status'], row['revision'], row['vendor'], row['amount_cents']),
                         ('confirmed', 2, 'Manually corrected vendor', 1940))
        self.assertEqual(self.confirmed_cost(), 1940)
        self.assertNotIn('vendor', response.get_json())

    def test_payment_candidate_does_not_replace_previously_confirmed_thousand_eur_cost(self):
        self.confirm_during_provider()
        path = self.app.config['SQLALCHEMY_DATABASE_URI'].removeprefix('sqlite:///')
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('UPDATE job_receipts SET amount_cents=100000 WHERE id=?', (self.receipt_id,))
            connection.commit()
        before = self.receipt()
        proposal = ai.validate_result(dict(
            RAW_RESULT, vendor='TEST Cestovná kancelária', receipt_date=None, amount='108.00',
            currency=None, document_type='payment_instruction',
        ))
        with patch('crm.ai_receipts.call_provider', return_value=proposal) as provider:
            response = self.extract({'revision': 1, 'manual': True})
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual((result['vendor'], result['detected_amount'], result['document_type']),
                         ('TEST Cestovná kancelária', '108.00', 'payment_instruction'))
        self.assertIsNone(result['amount'])
        self.assertIsNone(result['currency'])
        self.assertIsNone(result['receipt_date'])
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.receipt(), before)
        self.assertEqual(self.confirmed_cost(), 100000)

    def test_success_is_only_proposal_and_cache_avoids_second_paid_attempt(self):
        before = self.receipt()
        with patch('crm.ai_receipts.call_provider', return_value=dict(RESULT)) as provider:
            first = self.extract()
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.get_json()['amount'], '18.40')
            self.assertFalse(first.get_json()['cached'])
            second = self.extract()
            self.assertEqual(second.status_code, 200)
            self.assertTrue(second.get_json()['cached'])
            self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.receipt(), before)
        self.assertEqual(self.attempts(), [('success',)])
        self.assertEqual(first.headers['Cache-Control'], 'private, no-store')
        self.assertNotIn(DUMMY_KEY, first.get_data(as_text=True))
        page = self.fixture.request(f'/crm/receipts/{self.receipt_id}')
        self.assertNotIn(DUMMY_KEY, page.get_data(as_text=True))
        self.assertIn('0,00 €', self.fixture.request(f'/crm/jobs/{self.job_id}').get_data(as_text=True))

    def test_confirmation_while_api_waits_is_preserved_and_response_is_conflict(self):
        with patch('crm.ai_receipts.call_provider', side_effect=self.confirm_during_provider) as provider:
            response = self.extract()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(provider.call_count, 1)
        row = self.receipt()
        self.assertEqual((row['status'], row['revision'], row['vendor'], row['amount_cents']),
                         ('confirmed', 1, 'Manually corrected vendor', 1940))
        self.assertNotIn('vendor', response.get_json())

    def test_missing_key_or_corrupted_original_uses_no_provider_or_usage(self):
        before = self.receipt()
        self.app.config['CRM_OPENAI_API_KEY'] = ''
        with patch('crm.ai_receipts.call_provider') as provider:
            self.assertEqual(self.extract().status_code, 503)
            self.app.config['CRM_OPENAI_API_KEY'] = DUMMY_KEY
            original = Path(self.app.config['CRM_RECEIPT_FOLDER']) / before['object_name']
            original.write_bytes(b'corrupt synthetic original')
            self.assertEqual(self.extract().status_code, 503)
            provider.assert_not_called()
        self.assertEqual(self.receipt(), before)
        self.assertEqual(self.attempts(), [])

    def test_provider_failure_does_not_mutate_receipt_and_cooldown_prevents_retry(self):
        before = self.receipt()
        with patch('crm.ai_receipts.call_provider', side_effect=ai.ExtractionError('Synthetic safe timeout')) as provider:
            first = self.extract()
            self.assertEqual(first.status_code, 503)
            self.assertEqual(self.extract().status_code, 429)
            self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.receipt(), before)
        self.assertEqual(self.attempts(), [('failed',)])

    def test_unexpected_provider_exception_is_sanitized_without_key_leak(self):
        before = self.receipt()
        with patch('crm.ai_receipts.call_provider', side_effect=RuntimeError('Synthetic unexpected error: ' + DUMMY_KEY)):
            with self.assertLogs(self.app.logger, level='ERROR') as logs:
                response = self.extract()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(DUMMY_KEY, response.get_data(as_text=True))
        self.assertNotIn('Synthetic unexpected error', response.get_data(as_text=True))
        self.assertNotIn(DUMMY_KEY, '\n'.join(logs.output))
        self.assertEqual(self.receipt(), before)
        self.assertEqual(self.attempts(), [('failed',)])


class AiStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='crm-ai-state-test-')
        self.state = Path(self.temporary.name) / 'ai-state.sqlite3'
        self.network = patch('crm.ai_receipts.urllib.request.build_opener',
                             side_effect=AssertionError('Network calls prohibited in unit tests'))
        self.network.start()
        self.image = patch('crm.ai_receipts.image_data', return_value='data:image/jpeg;base64,synthetic')
        self.image.start()
        self.base = int(datetime(2026, 9, 16, 12, tzinfo=timezone.utc).timestamp())

    def tearDown(self):
        self.image.stop()
        self.network.stop()
        self.temporary.cleanup()

    def extract(self, number=1, user_id=1, daily_limit=30):
        return ai.extract_fields(DUMMY_KEY, self.state, user_id, f'{number:064x}',
                                 Path(self.temporary.name) / 'synthetic.png', daily_limit=daily_limit)

    def test_thirty_daily_attempts_are_persisted_and_thirty_first_is_blocked(self):
        with patch('crm.ai_receipts.call_provider', return_value=dict(RESULT)) as provider:
            for number in range(1, 31):
                with patch('crm.ai_receipts.time.time', return_value=self.base + number * 61):
                    self.extract(number)
            with patch('crm.ai_receipts.time.time', return_value=self.base + 31 * 61):
                with self.assertRaises(ai.ExtractionError) as error:
                    self.extract(31)
            self.assertEqual(error.exception.status, 429)
            self.assertEqual(provider.call_count, 30)
        with closing(sqlite3.connect(self.state)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 30)

    def test_six_per_minute_limit_is_shared_across_receipts_and_owners(self):
        with patch('crm.ai_receipts.call_provider', return_value=dict(RESULT)) as provider:
            with patch('crm.ai_receipts.time.time', return_value=self.base):
                for number in range(1, 7):
                    self.extract(number, user_id=number)
                with self.assertRaises(ai.ExtractionError) as error:
                    self.extract(7, user_id=7)
            self.assertEqual(error.exception.status, 429)
            self.assertEqual(provider.call_count, 6)

    def test_cache_is_owner_scoped_and_available_even_at_usage_limit(self):
        with patch('crm.ai_receipts.call_provider', return_value=dict(RESULT)) as provider:
            with patch('crm.ai_receipts.time.time', return_value=self.base):
                first = self.extract(daily_limit=1)
                cached = self.extract(daily_limit=1)
                self.assertFalse(first['cached'])
                self.assertTrue(cached['cached'])
                with self.assertRaises(ai.ExtractionError) as error:
                    self.extract(user_id=2, daily_limit=1)
            self.assertEqual(error.exception.status, 429)
            self.assertEqual(provider.call_count, 1)
            with patch('crm.ai_receipts.time.time', return_value=self.base + 86400):
                next_owner = self.extract(user_id=2, daily_limit=1)
            self.assertFalse(next_owner['cached'])
            self.assertEqual(provider.call_count, 2)

    def test_v2_does_not_reuse_v1_cache_with_unreadable_amount(self):
        legacy = dict(RESULT, amount=None, detected_amount=None)
        with patch('crm.ai_receipts.call_provider', side_effect=[legacy, dict(RESULT)]) as provider:
            with patch('crm.ai_receipts.time.time', return_value=self.base):
                with patch('crm.ai_receipts.PROMPT_VERSION', 'receipt-total-v1'):
                    first = self.extract()
                self.assertIsNone(first['amount'])
                self.assertEqual(ai.PROMPT_VERSION, 'receipt-total-v2')
                fresh = self.extract()
                self.assertFalse(fresh['cached'])
                self.assertEqual(fresh['amount'], '18.40')
                self.assertTrue(self.extract()['cached'])
            self.assertEqual(provider.call_count, 2)

    def test_failed_attempt_counts_towards_budget_and_retry_waits_sixty_seconds(self):
        with patch('crm.ai_receipts.call_provider', side_effect=[ai.ExtractionError('Safe synthetic timeout'), dict(RESULT)]) as provider:
            with patch('crm.ai_receipts.time.time', return_value=self.base):
                with self.assertRaises(ai.ExtractionError):
                    self.extract()
                with self.assertRaises(ai.ExtractionError) as error:
                    self.extract()
                self.assertEqual(error.exception.status, 429)
            self.assertEqual(provider.call_count, 1)
            with patch('crm.ai_receipts.time.time', return_value=self.base + 61):
                with self.assertRaises(ai.ExtractionError) as error:
                    self.extract(daily_limit=1)
                self.assertEqual(error.exception.status, 429)
            self.assertEqual(provider.call_count, 1)
            with patch('crm.ai_receipts.time.time', return_value=self.base + 61):
                retry = self.extract()
            self.assertFalse(retry['cached'])
            self.assertEqual(provider.call_count, 2)

    def test_overlapping_same_receipt_reserves_only_one_provider_attempt(self):
        entered, release = threading.Event(), threading.Event()
        answers, errors = [], []

        def provider(*args):
            entered.set()
            if not release.wait(5):
                raise AssertionError('Synthetic provider release timed out')
            return dict(RESULT)

        def worker():
            try:
                answers.append(self.extract())
            except Exception as error:
                errors.append(error)

        with patch('crm.ai_receipts.call_provider', side_effect=provider) as mocked:
            with patch('crm.ai_receipts.time.time', return_value=self.base):
                thread = threading.Thread(target=worker)
                thread.start()
                try:
                    self.assertTrue(entered.wait(5))
                    with self.assertRaises(ai.ExtractionError) as error:
                        self.extract()
                    self.assertEqual(error.exception.status, 409)
                finally:
                    release.set()
                    thread.join(5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(mocked.call_count, 1)
        self.assertEqual(errors, [])
        self.assertEqual(len(answers), 1)
        with closing(sqlite3.connect(self.state)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 1)


class AiValidationTests(unittest.TestCase):
    def test_exact_cents_date_and_currency_are_validated(self):
        result = ai.validate_result(dict(RAW_RESULT))
        self.assertEqual((result['vendor'], result['receipt_date'], result['amount']),
                         ('TEST Elektro', '2026-09-16', '18.40'))
        self.assertEqual((result['detected_amount'], result['currency'], result['document_type']),
                         ('18.40', 'EUR', 'receipt'))
        for change in (
            {'receipt_date': '2026-02-30'}, {'amount': '-18.40'}, {'amount': '18,40'},
            {'amount': '18.4'}, {'amount': '0.00'}, {'amount': '18.400'},
            {'amount': '10000000.01'}, {'vendor': 'a' * 121}, {'amount': 18.40},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ai.ExtractionError):
                    ai.validate_result(dict(RAW_RESULT, **change))
        foreign = ai.validate_result(dict(RAW_RESULT, currency='USD'))
        self.assertIsNone(foreign['amount'])
        self.assertEqual((foreign['detected_amount'], foreign['currency']), ('18.40', 'USD'))
        unreadable = ai.validate_result(dict(RAW_RESULT, vendor=None, receipt_date=None, amount=None))
        self.assertIsNone(unreadable['amount'])

    def test_schema_rejects_missing_extra_fields_and_other_document_total(self):
        for value in (None, [], {}, dict(RAW_RESULT, unexpected='field')):
            with self.subTest(value=value):
                with self.assertRaises(ai.ExtractionError):
                    ai.validate_result(value)
        other = ai.validate_result(dict(RAW_RESULT, document_type='other'))
        self.assertIsNone(other['amount'])
        self.assertIsNone(other['detected_amount'])

    def test_credit_note_does_not_become_positive_expense(self):
        for amount in ('18.40', '-18.40', None):
            with self.subTest(amount=amount):
                result = ai.validate_result(dict(RAW_RESULT, document_type='credit_note', amount=amount))
                self.assertIsNone(result['amount'])
                self.assertIsNone(result['detected_amount'])

    def test_payment_instruction_without_visible_currency_or_issue_date_returns_candidate_only(self):
        raw = dict(RAW_RESULT, vendor='TEST Cestovná kancelária', receipt_date=None, amount='108.00',
                   currency=None, document_type='payment_instruction')
        result = ai.validate_result(raw)
        self.assertEqual((result['vendor'], result['detected_amount'], result['document_type']),
                         ('TEST Cestovná kancelária', '108.00', 'payment_instruction'))
        self.assertIsNone(result['amount'])
        self.assertIsNone(result['currency'])
        self.assertIsNone(result['receipt_date'])
        self.assertIn('pokyn k platbe', result['message'])
        self.assertIn('nie celkovú sumu faktúry', result['message'])
        self.assertIn('výslovne potvrďte', result['message'])
        self.assertIn('EUR', result['message'])
        for blank_currency in ('', '  '):
            with self.subTest(blank_currency=blank_currency):
                blank = ai.validate_result(dict(raw, currency=blank_currency))
                self.assertIsNone(blank['currency'])
                self.assertIsNone(blank['amount'])
                self.assertEqual(blank['detected_amount'], '108.00')

    def test_payment_instruction_with_visible_eur_returns_payment_amount_not_invoice_total(self):
        result = ai.validate_result(dict(RAW_RESULT, amount='108.00', receipt_date=None,
                                         document_type='payment_instruction'))
        self.assertEqual((result['amount'], result['detected_amount'], result['currency']),
                         ('108.00', '108.00', 'EUR'))
        self.assertIsNone(result['receipt_date'])
        self.assertIn('nie celkovú sumu faktúry', result['message'])

    def test_payment_instruction_foreign_currency_is_not_converted_to_eur(self):
        result = ai.validate_result(dict(RAW_RESULT, amount='108.00', currency='CZK',
                                         document_type='payment_instruction'))
        self.assertIsNone(result['amount'])
        self.assertEqual((result['detected_amount'], result['currency']), ('108.00', 'CZK'))
        self.assertIn('neprevádza na EUR', result['message'])
        for amount in ('-108.00', '0.00', '108,00', '108.001'):
            with self.subTest(amount=amount):
                with self.assertRaises(ai.ExtractionError):
                    ai.validate_result(dict(RAW_RESULT, amount=amount, currency=None,
                                            document_type='payment_instruction'))

    def test_legacy_invoice_and_receipt_keep_exact_eur_amount_and_classification(self):
        for document_type in ('invoice', 'receipt'):
            with self.subTest(document_type=document_type):
                result = ai.validate_result(dict(RAW_RESULT, document_type=document_type))
                self.assertEqual((result['amount'], result['detected_amount'], result['currency']),
                                 ('18.40', '18.40', 'EUR'))
                self.assertEqual(result['document_type'], document_type)
                self.assertNotIn('pokyn k platbe', result['message'])

    def test_provider_transport_errors_do_not_expose_key_or_response_body(self):
        failures = (
            TimeoutError('Synthetic timeout with ' + DUMMY_KEY),
            urllib.error.HTTPError(ai.API_URL, 429, 'Synthetic ' + DUMMY_KEY, {}, BytesIO(DUMMY_KEY.encode())),
            urllib.error.HTTPError(ai.API_URL, 401, 'Synthetic ' + DUMMY_KEY, {}, BytesIO(DUMMY_KEY.encode())),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                opener = Mock()
                opener.open.side_effect = failure
                with patch('crm.ai_receipts.urllib.request.build_opener', return_value=opener):
                    with self.assertRaises(ai.ExtractionError) as error:
                        ai.call_provider(DUMMY_KEY, 'data:image/jpeg;base64,synthetic')
                self.assertNotIn(DUMMY_KEY, str(error.exception))
                self.assertEqual(error.exception.status, 503)
                self.assertEqual(opener.open.call_count, 1)

    def test_malformed_provider_json_is_safe_failure(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = ('not-json ' + DUMMY_KEY).encode()
        opener = Mock()
        opener.open.return_value = response
        with patch('crm.ai_receipts.urllib.request.build_opener', return_value=opener):
            with self.assertRaises(ai.ExtractionError) as error:
                ai.call_provider(DUMMY_KEY, 'data:image/jpeg;base64,synthetic')
        self.assertNotIn(DUMMY_KEY, str(error.exception))
        self.assertEqual(opener.open.call_count, 1)

    def test_mocked_provider_payment_response_preserves_unknown_currency_and_issue_date(self):
        raw = dict(RAW_RESULT, vendor='TEST Cestovná kancelária', receipt_date=None, amount='108.00',
                   currency=None, document_type='payment_instruction')
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({
            'status': 'completed', 'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(raw)},
            ]}],
        }).encode()
        opener = Mock()
        opener.open.return_value = response
        with patch('crm.ai_receipts.urllib.request.build_opener', return_value=opener):
            result = ai.call_provider(DUMMY_KEY, 'data:image/jpeg;base64,synthetic')
        self.assertEqual(result['detected_amount'], '108.00')
        self.assertEqual(result['document_type'], 'payment_instruction')
        self.assertIsNone(result['amount'])
        self.assertIsNone(result['currency'])
        self.assertIsNone(result['receipt_date'])
        self.assertEqual(opener.open.call_count, 1)


if __name__ == '__main__':
    unittest.main()
