// Hardcoded chat threads — no real AI calls
export const conversations = [
  { id: 'c1', title: 'Handle INV-1001', preview: 'Second reminder required.', time: 'Now' },
  { id: 'c2', title: 'Weekly Collection Review', preview: '7 invoices aging past 15 days.', time: '1h' },
  { id: 'c3', title: 'Customer Escalation', preview: 'Helios Retail moved to high risk.', time: '3h' },
  { id: 'c4', title: 'Promise-to-Pay Audit', preview: 'NovaTech PTP recorded.', time: 'Yesterday' },
]

export const sampleMessages = [
  { id: 1, role: 'user', text: 'Handle invoice INV-1001' },
  { id: 2, role: 'ai', text: 'Checking invoice details...' },
  { id: 3, role: 'ai', text: 'Retrieving customer payment history...' },
  { id: 4, role: 'ai', text: 'Analyzing payment behavior...' },
  { id: 5, role: 'ai', text: 'Second reminder required.' },
  { id: 6, role: 'ai', text: 'Reminder email drafted successfully.' },
]
