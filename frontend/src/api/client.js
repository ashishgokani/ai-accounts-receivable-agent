/**
 * API Client for Autonomous Accounts Receivable Management Backend.
 * Connects frontend UI to FastAPI REST endpoints.
 */

const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api').replace(/\/$/, '');

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  try {
    const response = await fetch(url, config);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Request failed with status ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`API Error on ${endpoint}:`, error);
    throw error;
  }
}

// ==================== Analytics & Dashboard ====================
export async function getDashboardMetrics() {
  return request('/analytics/dashboard');
}

// ==================== Invoices ====================
export async function getInvoices(params = {}) {
  const query = new URLSearchParams();
  if (params.status && params.status !== 'All') query.append('status', params.status);
  if (params.search) query.append('search', params.search);
  const qStr = query.toString() ? `?${query.toString()}` : '';
  return request(`/invoices${qStr}`);
}

export async function getInvoiceDetails(invoiceId) {
  return request(`/invoices/${invoiceId}`);
}

export async function createInvoice(data) {
  return request('/invoices', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateInvoice(invoiceId, data) {
  return request(`/invoices/${invoiceId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function sendInvoiceReminder(invoiceId) {
  return request(`/invoices/${invoiceId}/remind`, { method: 'POST' });
}

// ==================== Customers ====================
export async function getCustomers(params = {}) {
  const query = new URLSearchParams();
  if (params.status) query.append('status', params.status);
  if (params.risk && params.risk !== 'All') query.append('risk', params.risk);
  if (params.search) query.append('search', params.search);
  const qStr = query.toString() ? `?${query.toString()}` : '';
  return request(`/customers${qStr}`);
}

export async function getCustomerDetails(customerId) {
  return request(`/customers/${customerId}`);
}

export async function createCustomer(data) {
  return request('/customers', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateCustomer(customerId, data) {
  return request(`/customers/${customerId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function removeCustomer(customerId) {
  return request(`/customers/${customerId}`, { method: 'DELETE' });
}

export async function restoreCustomer(customerId) {
  return request(`/customers/${customerId}/restore`, { method: 'POST' });
}

// ==================== Automation Pipeline ====================
export async function getAutomationStatus() {
  return request('/automation/status');
}

export async function getAutomationPipeline() {
  return request('/automation/pipeline');
}

export async function getAutomationHistory() {
  return request('/automation/history');
}

export async function triggerAutomationCycle() {
  return request('/automation/run-now', { method: 'POST' });
}

// ==================== AI Agent & Chat ====================
export async function getChatConfig(sessionId = null) {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return request(`/agent/config${query}`);
}

export async function getChatSessions() {
  return request('/agent/sessions');
}

export async function createChatSession(title = 'New Conversation') {
  return request('/agent/sessions', {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export async function getSessionMessages(sessionId) {
  return request(`/agent/sessions/${sessionId}/messages`);
}

export async function getActiveSessionTurn(sessionId) {
  if (!sessionId) return { is_active: false, status: 'IDLE' };
  return request(`/agent/sessions/${encodeURIComponent(sessionId)}/active-turn`);
}

export async function deleteChatSession(sessionId) {
  return request(`/agent/sessions/${sessionId}`, { method: 'DELETE' });
}

export async function renameChatSession(sessionId, title) {
  return request(`/agent/sessions/${sessionId}`, {
    method: 'PUT',
    body: JSON.stringify({ title }),
  });
}

export async function sendChatMessage(message, sessionId = null) {
  return request('/agent/chat', {
    method: 'POST',
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

export async function streamChatMessage(message, sessionId, callbacks = {}) {
  const { onSessionInfo, onThought, onStatus, onContent, onDone, onError } = callbacks;
  const url = `${API_BASE_URL}/agent/chat/stream`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message, session_id: sessionId }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed with status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (data.type === 'session_info' && onSessionInfo) {
              onSessionInfo(data);
            } else if (data.type === 'thought' && onThought) {
              onThought(data.chunk);
            } else if (data.type === 'status' && onStatus) {
              onStatus(data.message);
            } else if (data.type === 'content' && onContent) {
              onContent(data.chunk);
            } else if (data.type === 'done' && onDone) {
              onDone(data);
            }
          } catch (pErr) {
            console.error('Failed to parse SSE line:', trimmed, pErr);
          }
        }
      }
    }
  } catch (error) {
    console.error('Streaming API Error:', error);
    if (onError) onError(error);
    throw error;
  }
}

export async function triggerAutonomousRun() {
  return request('/agent/run-autonomous', { method: 'POST' });
}

export async function getAgentActivity(page = 1, pageSize = 10, filters = {}) {
  const query = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  });
  if (typeof filters === 'string') {
    query.append('session_id', filters);
  } else if (filters) {
    if (filters.sessionId) query.append('session_id', filters.sessionId);
    if (filters.search) query.append('search', filters.search);
    if (filters.status && filters.status !== 'All') query.append('status', filters.status);
    if (filters.actionType && filters.actionType !== 'All') query.append('action_type', filters.actionType);
    if (filters.startDate) query.append('start_date', filters.startDate);
    if (filters.endDate) query.append('end_date', filters.endDate);
  }
  return request(`/agent/activity?${query.toString()}`);
}

export async function searchChatHistory(query) {
  if (!query || !query.trim()) return [];
  const qStr = new URLSearchParams({ q: query.trim() }).toString();
  return request(`/agent/chat/search?${qStr}`);
}

// ==================== Human Approvals ====================
export async function getPendingApprovals() {
  return request('/approvals');
}

export async function reviewApproval(
  approvalId,
  status,
  reviewNotes = '',
  reviewedBy = 'Ashish Gokani (Admin)',
  customSubject = null,
  customBody = null,
  amountReceived = null
) {
  return request(`/approvals/${approvalId}/decision`, {
    method: 'POST',
    body: JSON.stringify({
      status,
      review_notes: reviewNotes,
      reviewed_by: reviewedBy,
      custom_subject: customSubject,
      custom_body: customBody,
      amount_received: amountReceived ? Number(amountReceived) : null,
    }),
  });
}

// ==================== Simulation & Demo ====================
export async function simulateCustomerReply(invoiceId, replyMessage) {
  return request('/simulation/customer-reply', {
    method: 'POST',
    body: JSON.stringify({
      invoice_id: invoiceId,
      reply_message: replyMessage,
    }),
  });
}

export async function simulatePayment(invoiceId, amount, paymentMethod = 'NEFT', referenceNumber = null) {
  return request('/simulation/record-payment', {
    method: 'POST',
    body: JSON.stringify({
      invoice_id: invoiceId,
      amount: parseFloat(amount),
      payment_method: paymentMethod,
      reference_number: referenceNumber || `NEFT/${Date.now().toString().slice(-6)}`,
    }),
  });
}

// ==================== Admin Settings ====================
export async function getAdminSettings() {
  return request('/settings');
}

export async function updatePenaltySettings(data) {
  return request('/settings/penalty', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateReminderSettings(data) {
  return request('/settings/reminders', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateBankSettings(data) {
  return request('/settings/bank', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function updateAgentSettings(data) {
  return request('/settings/agent', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

