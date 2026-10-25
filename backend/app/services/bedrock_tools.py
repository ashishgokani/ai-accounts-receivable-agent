"""
AWS Bedrock Tool Specifications in Converse API JSON Schema Format.

Defines schemas for all deterministic Accounts Receivable tools available
to the Amazon Nova Pro / Claude reasoning agents.
"""

from typing import List, Dict, Any

BEDROCK_TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "toolSpec": {
            "name": "get_overdue_invoices",
            "description": "Retrieve all invoices that are currently past their due date.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "min_days": {
                            "type": "integer",
                            "description": "Minimum days past due date (default: 0).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of records to return.",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_invoice_details",
            "description": "Retrieve detailed information for a specific invoice ID (e.g. INV-1024).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {
                            "type": "string",
                            "description": "The unique invoice identifier (e.g. INV-1024).",
                        }
                    },
                    "required": ["invoice_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_customers",
            "description": "Retrieve directory of corporate debtors and customers with total counts, risk tiers, and outstanding balances. Use when user asks 'how many customers are there?', 'show customer directory', or 'list all customers'.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by status: ACTIVE, ARCHIVED, or ALL (default: ACTIVE).",
                        },
                        "risk_level": {
                            "type": "string",
                            "description": "Optional filter by risk tier: Low, Medium, or High.",
                        },
                        "search": {
                            "type": "string",
                            "description": "Optional search term to match customer name, company, email, or ID.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of customers to return (default: 50).",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_customer_history",
            "description": "Retrieve customer payment track record, credit risk score, and previous invoice count.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "Customer ID (e.g. CUST-001) or company name (e.g. ABC Ltd).",
                        }
                    },
                    "required": ["customer_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "draft_reminder_email",
            "description": "Draft a personalized payment reminder email with factual invoice and penalty amounts.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Target invoice ID."},
                        "reminder_level": {
                            "type": "integer",
                            "description": "Reminder stage: 1 (polite), 2 (firm with penalty), 3 (urgent notice).",
                        },
                        "tone": {"type": "string", "description": "Tone: polite, firm, or urgent."},
                    },
                    "required": ["invoice_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "send_email",
            "description": "Dispatch a reminder email to the customer. Guardrails will verify safety and pause high-value cases for approval.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Invoice ID to remind."},
                        "subject": {"type": "string", "description": "Email subject line."},
                        "body": {
                            "type": "string",
                            "description": "Complete email body. MUST NOT contain bracketed placeholders like [Your Company Name] or [Your Name]. Always sign off as:\nWarm regards,\nAccounts Receivable Team\nReceivIQ.",
                        },
                        "recipient": {"type": "string", "description": "Recipient email address."},
                    },
                    "required": ["invoice_id", "subject", "body"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "update_invoice_status",
            "description": "Update invoice state (PENDING, PAID, OVERDUE, PAYMENT_PROMISED, DISPUTED, ESCALATED).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Target invoice ID."},
                        "new_status": {"type": "string", "description": "New target status."},
                        "notes": {"type": "string", "description": "Optional notes or dispute reason."},
                    },
                    "required": ["invoice_id", "new_status"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_escalation",
            "description": "Escalate high-risk or prolonged overdue invoice to management for legal action or credit freeze.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Invoice to escalate."},
                        "reason": {"type": "string", "description": "Detailed justification for escalation."},
                    },
                    "required": ["invoice_id", "reason"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "record_payment",
            "description": "Record payment received, mark invoice PAID, auto-cancel reminders, and dispatch receipt.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Settled invoice ID."},
                        "amount": {"type": "number", "description": "Amount received in Rupees."},
                        "payment_method": {"type": "string", "description": "NEFT, RTGS, UPI, etc."},
                        "reference_number": {"type": "string", "description": "Bank transaction reference."},
                    },
                    "required": ["invoice_id", "amount"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_customer",
            "description": "Onboard a new corporate customer into the database.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Billing contact representative name."},
                        "company_name": {"type": "string", "description": "Company / business legal entity name."},
                        "email": {"type": "string", "description": "Corporate billing email address."},
                        "phone": {"type": "string", "description": "Phone number."},
                        "address": {"type": "string", "description": "Office address."},
                        "risk_level": {"type": "string", "description": "Low, Medium, or High."},
                    },
                    "required": ["name", "company_name", "email"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "remove_customer",
            "description": "Archive a customer to the Removed Section. Fails if the customer has unpaid pending/overdue invoices.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Customer ID (e.g. CUST-001) or company name."},
                    },
                    "required": ["customer_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_invoice",
            "description": "Create a new receivable invoice for a customer.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Target Customer ID."},
                        "invoice_number": {"type": "string", "description": "Unique invoice number (e.g. INV-1099)."},
                        "amount": {"type": "number", "description": "Invoice billing amount in Rupees."},
                        "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD format."},
                    },
                    "required": ["customer_id", "invoice_number", "amount", "due_date"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "send_bulk_settlement_offer",
            "description": "Send promotional early-settlement discount offers to customers with pending or overdue balances if paid within a specified timeframe (e.g. 0.1% discount within 24 hours).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "discount_percent": {
                            "type": "number",
                            "description": "Discount percentage to offer (e.g. 0.1 or 2.0).",
                        },
                        "hours_valid": {
                            "type": "integer",
                            "description": "Number of hours the discount offer is valid for (default: 24).",
                        },
                        "min_amount": {
                            "type": "number",
                            "description": "Optional minimum outstanding balance in Rupees (e.g. 200000 for 2 lakh or more).",
                        },
                        "custom_message": {
                            "type": "string",
                            "description": "Optional custom settlement note from the administrator.",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "send_custom_communication",
            "description": "Universal omnichannel communication tool. Send any arbitrary email message to filtered cohorts or individual debtors.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string", "description": "Email subject header."},
                        "message_body": {
                            "type": "string",
                            "description": "The complete email body. MUST NOT contain bracketed placeholders like [Your Company Name] or [Your Name]. Always sign off as:\nWarm regards,\nAccounts Receivable Team\nReceivIQ.",
                        },
                        "target_criteria": {"type": "object", "description": "Recipient filter criteria."},
                        "comm_type": {"type": "string", "description": "Category tag for audit trail."},
                    },
                    "required": ["subject", "message_body"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "grant_grace_period",
            "description": "Grant a payment extension and pause automated collection reminders until a future date.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Target invoice ID."},
                        "days": {"type": "integer", "description": "Number of extension days granted."},
                        "reason": {"type": "string", "description": "Administrative reason for the extension."},
                    },
                    "required": ["invoice_id", "days"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "revoke_commitment",
            "description": "Revoke an active commercial agreement or settlement discount offer and restore contractual terms.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Optional target invoice ID."},
                        "commitment_type": {"type": "string", "description": "Optional agreement type to revoke."},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_communication_history",
            "description": "Retrieve chronological audit log of sent reminder emails, settlement offers, and customer notices.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Optional invoice ID to filter communications (e.g. INV-1004)."},
                        "customer_id": {"type": "string", "description": "Optional customer ID to filter communications."},
                        "limit": {"type": "integer", "description": "Maximum number of dispatches to return (default: 10)."},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_invoice_commitments",
            "description": "Retrieve active and historical commercial agreements, settlement discounts, and grace periods registered for invoices.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Optional target invoice ID."},
                        "customer_id": {"type": "string", "description": "Optional customer ID."},
                        "status": {"type": "string", "description": "Optional filter: ACTIVE, EXPIRED, REVOKED, FULFILLED."},
                        "limit": {"type": "integer", "description": "Maximum records to return (default: 10)."},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "update_customer_profile",
            "description": "Update customer master data such as contact name, company name, email, phone, office address, risk score, or risk level (Low, Medium, High).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Customer ID (e.g. CUST-001) or company name."},
                        "name": {"type": "string", "description": "Billing contact name."},
                        "company_name": {"type": "string", "description": "Company name."},
                        "email": {"type": "string", "description": "Corporate billing email."},
                        "phone": {"type": "string", "description": "Phone number."},
                        "address": {"type": "string", "description": "Physical office address."},
                        "risk_level": {"type": "string", "description": "Low, Medium, or High."},
                        "risk_score": {"type": "integer", "description": "Credit risk score (0-100)."},
                    },
                    "required": ["customer_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "update_invoice_data",
            "description": "Update invoice parameters such as due date, amount, dispute notes, or promised payment date. Settled PAID invoices are immutable under financial compliance rules.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string", "description": "Target invoice ID or number (e.g. INV-1004)."},
                        "due_date": {"type": "string", "description": "New due date in YYYY-MM-DD format."},
                        "amount": {"type": "number", "description": "Adjusted principal billing amount."},
                        "status": {"type": "string", "description": "PENDING, OVERDUE, DISPUTED, PAYMENT_PROMISED, ESCALATED."},
                        "dispute_reason": {"type": "string", "description": "Dispute notes or reason."},
                        "promised_payment_date": {"type": "string", "description": "Promised settlement date in YYYY-MM-DD format."},
                    },
                    "required": ["invoice_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "trigger_automation_cycle",
            "description": "Immediately execute the autonomous background AR monitoring and collection pipeline.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_pending_approvals",
            "description": "Retrieve all pending human-in-the-loop managerial approvals (e.g. high-value escalations or legal notices).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "review_approval_decision",
            "description": "Approve or reject a pending human-in-the-loop action request (e.g. approve escalation).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "approval_id": {"type": "string", "description": "The approval ID (e.g. APP-001)."},
                        "decision": {"type": "string", "description": "APPROVED or REJECTED."},
                        "notes": {"type": "string", "description": "Optional supervisor review notes."},
                    },
                    "required": ["approval_id", "decision"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_financial_portfolio_summary",
            "description": "Retrieve comprehensive financial KPIs, portfolio aging, total outstanding debt, and collection efficiency for the entire project.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_agent_audit_logs",
            "description": "Retrieve chronological audit log of autonomous decisions, tool invocations, and ledger mutations.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Maximum number of audit events to return (default: 10)."},
                    },
                }
            },
        }
    },
]
