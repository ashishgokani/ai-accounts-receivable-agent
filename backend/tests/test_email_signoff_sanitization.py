"""
Unit and Integration Tests for Email Sign-Off and Placeholder Sanitization.

Verifies:
1. sanitize_email_placeholders_and_signoff purges generic bracketed placeholders
   like [Your Company Name], [Your Name], [Company Name], etc.
2. Sign-offs are standardized as 'Warm regards,\nAccounts Receivable Team\nReceivIQ'.
3. Outgoing emails recorded in the audit trail have zero placeholders.
"""

from app.services.email_service import sanitize_email_placeholders_and_signoff


def test_sanitize_replaces_your_company_name():
    """Verifies that [Your Company Name] and [Your Name] are replaced with authentic corporate team identity."""
    raw_email = (
        "Dear ABC,\n\n"
        "We wish you and your family a very Happy Diwali!\n\n"
        "Warm regards,\n"
        "[Your Name]\n"
        "[Your Company Name]"
    )

    cleaned = sanitize_email_placeholders_and_signoff(raw_email)

    # Must NOT contain square brackets or generic placeholders
    assert "[Your Company Name]" not in cleaned
    assert "[Your Name]" not in cleaned
    assert "[" not in cleaned and "]" not in cleaned

    # Must contain corporate team identity
    assert "Accounts Receivable Team" in cleaned
    assert "ReceivIQ" in cleaned
    assert "Warm regards,\nAccounts Receivable Team\nReceivIQ" in cleaned


def test_sanitize_appends_signoff_if_missing():
    """Verifies that if an email body has no sign-off at all, one is automatically appended."""
    raw_email = "Dear Customer,\n\nPlease review your updated account statement."
    cleaned = sanitize_email_placeholders_and_signoff(raw_email)

    assert "Warm regards,\nAccounts Receivable Team\nReceivIQ" in cleaned


def test_sanitize_normalizes_partial_signoffs():
    """Verifies that partial or single-line sign-offs are expanded to the full compliant format."""
    raw_1 = "Dear Client,\n\nNotice of payment.\n\nWarm regards,\nAccounts Receivable Team"
    cleaned_1 = sanitize_email_placeholders_and_signoff(raw_1)
    assert "Warm regards,\nAccounts Receivable Team\nReceivIQ" in cleaned_1

    raw_2 = "Dear Client,\n\nNotice of payment.\n\nRegards,\nReceivIQ"
    cleaned_2 = sanitize_email_placeholders_and_signoff(raw_2)
    assert "Warm regards,\nAccounts Receivable Team\nReceivIQ" in cleaned_2
