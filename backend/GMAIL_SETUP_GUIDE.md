# Google Gmail Integration & External Mailbox Configuration Guide

This guide provides step-by-step instructions to configure incoming email detection and outgoing responses for the Autonomous Accounts Receivable Management Platform.

---

## Architecture Overview

All platform collection reminder emails are dispatched with:
```http
Reply-To: ashishgokani58@gmail.com
X-AR-Invoice-ID: INV-XXXX
X-AR-Customer-ID: CUST-XXXX
```

When a debtor replies:
1. The email arrives at `ashishgokani58@gmail.com` (or your configured Google inbox).
2. The platform's **Inbound Email Listener** polls the inbox via **Gmail API with OAuth 2.0** or **IMAP SSL (Port 993)**.
3. The **AI Reply Processor** parses the incoming message:
   - Strips quoted email threads to prevent recursive instruction processing.
   - Verifies the sender address against registered customer accounts in PostgreSQL. Unrecognized senders are rejected immediately with zero customer data leakage.
   - Uses **Amazon Nova Pro** to classify intent (`PAYMENT_CLAIMED`, `PAYMENT_PROMISED`, `INVOICE_DISPUTE`, `EXTENSION_REQUEST`, `GENERAL_INQUIRY`, `UNKNOWN_OR_AMBIGUOUS`).
   - Extracts UTR numbers, promised payment dates, and claimed amounts.
4. **Human-in-the-Loop Approval Gating**:
   - Consequential actions (payment claims, disputes, waivers, partial payments) route to the **Manager Approvals Queue** with the exact receipt timestamp and UTR number.
   - An immediate contextual acknowledgment email is sent to the customer with `Reply-To: ashishgokani58@gmail.com`.

---

## Option 1: Gmail IMAP SSL with App Password (Fastest & Recommended)

Google requires an **App Password** for server-to-server IMAP SSL connections. Standard account passwords will not work if Two-Step Verification is enabled.

### Step 1: Enable IMAP in Gmail Settings
1. Open [Gmail](https://mail.google.com/) and click the **Settings (gear icon)** in the top right -> **See all settings**.
2. Navigate to the **Forwarding and POP/IMAP** tab.
3. Under **IMAP access**, select **Enable IMAP**.
4. Click **Save Changes** at the bottom.

### Step 2: Generate a 16-Character Google App Password
1. Visit your [Google Account Security Settings](https://myaccount.google.com/security).
2. Ensure **2-Step Verification** is turned **ON**.
3. In the search bar at the top of your Google Account page, search for **App passwords**.
4. Click **App passwords**.
5. Under **App name**, enter a descriptive name (e.g. `AR Platform Inbound Listener`).
6. Click **Create**.
7. Google will display a 16-character code (e.g. `abcd efgh ijkl mnop`).
8. Copy this code without spaces.

### Step 3: Configure `.env` in `backend/`
Add or update the following environment variables in `backend/.env`:
```env
# Outgoing Email Configuration (SMTP)
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=ashishgokani58@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
FROM_EMAIL=ashishgokani58@gmail.com
FROM_NAME=AR Collection Agent
REPLY_TO_EMAIL=ashishgokani58@gmail.com

# Inbound Email Detection (IMAP SSL Port 993)
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=ashishgokani58@gmail.com
IMAP_PASSWORD=abcdefghijklmnop
IMAP_POLLING_ENABLED=true
IMAP_POLL_INTERVAL_SECONDS=30
```

---

## Option 2: Gmail API with OAuth 2.0 (Google Cloud Console)

If your enterprise policy mandates OAuth 2.0 token-based access:

### Step 1: Create a Project in Google Cloud Console
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project named `AR-Receivable-Agent`.
3. In the left navigation menu, go to **APIs & Services** -> **Library**.
4. Search for **Gmail API** and click **Enable**.

### Step 2: Configure OAuth Consent Screen
1. Go to **APIs & Services** -> **OAuth consent screen**.
2. Select **External** (or **Internal** for Google Workspace) and click **Create**.
3. Fill in:
   - **App name**: `AR Intelligence Agent`
   - **User support email**: `ashishgokani58@gmail.com`
   - **Developer contact information**: `ashishgokani58@gmail.com`
4. On the **Scopes** page, add:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/gmail.send`
5. On the **Test users** page, add `ashishgokani58@gmail.com`.
6. Save and finish.

### Step 3: Create OAuth 2.0 Client ID Credentials
1. Go to **APIs & Services** -> **Credentials**.
2. Click **+ Create Credentials** -> **OAuth client ID**.
3. Select **Application type**: **Desktop app**.
4. Name it `AR Desktop Agent`.
5. Click **Create** and download the JSON file.
6. Rename this file to `credentials.json` and place it in `backend/credentials.json`.

### Step 4: Configure `.env`
```env
GMAIL_API_ENABLED=true
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json
REPLY_TO_EMAIL=ashishgokani58@gmail.com
```

---

## Testing & Verification

1. **Simulation Route**:
   You can simulate customer email replies anytime via the interactive UI simulation panel or via POST to `/api/simulation/customer-reply`:
   ```bash
   curl -X POST "http://localhost:8000/api/simulation/customer-reply" \
     -H "Content-Type: application/json" \
     -d '{"invoice_id": "INV-001", "reply_message": "We have paid ₹50,000 today via NEFT. UTR reference is AXIS98112233."}'
   ```
2. **Inbox Check**:
   The background scheduler checks the inbox automatically on each cycle pass. You can also trigger an immediate cycle by clicking **"Run Agent Now"** on the Dashboard.
