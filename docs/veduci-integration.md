# Vedúci integration

InvoiceMakerAI owns its database. Vedúci accesses only an explicit HTTPS API and never receives
database credentials.

## Configuration

Configure both values together. The integration stays disabled when both are absent.

```dotenv
VEDUCI_INTEGRATION_TOKEN=<random value with at least 32 characters>
VEDUCI_INTEGRATION_USER_ID=<InvoiceMaker user ID>
```

Generate the token with a password manager or `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Store the same token as `INVOICEMAKER_API_TOKEN` in Vedúci. Never commit it.

## First read-only capability

```http
GET /api/v1/integrations/veduci/invoices/overdue
Authorization: Bearer <token>
Accept: application/json
```

The response contains only the configured user's overdue invoices. It excludes client email,
address, tax identifiers, bank details and invoice PDF paths. Amounts are JSON strings to avoid
floating-point changes in transit, and totals are separated by currency.

```json
{
  "as_of": "2026-08-17",
  "count": 1,
  "totals_by_currency": {"EUR": "1230.00"},
  "invoices": [
    {
      "id": 42,
      "invoice_number": "2026-014",
      "client_name": "Elektro ABC",
      "amount": "1230.00",
      "currency": "EUR",
      "due_date": "2026-08-01",
      "days_overdue": 16
    }
  ]
}
```

The endpoint is GET-only, sets `Cache-Control: no-store`, returns `401` for an invalid token and
`503` when integration configuration is incomplete or points to a missing user.

Future write actions must use a separate confirmation workflow. An LLM must never call email,
invoice creation or payment-state mutations directly.
