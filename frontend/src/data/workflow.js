// Dummy workflow steps for Agent Activity page
export const timelineSteps = [
  { id: 1, title: 'Request Received', time: '09:14:02', status: 'Complete', detail: 'User asked to handle INV-1001.' },
  { id: 2, title: 'Invoice Retrieved', time: '09:14:04', status: 'Complete', detail: 'Loaded INV-1001 · ABC Ltd · $12,400.' },
  { id: 3, title: 'Customer History Retrieved', time: '09:14:07', status: 'Complete', detail: '18 invoices, 4 late payments in 90 days.' },
  { id: 4, title: 'Risk Analysis Completed', time: '09:14:09', status: 'Complete', detail: 'Risk score 82 · High · Delayed pattern.' },
  { id: 5, title: 'Reminder Generated', time: '09:14:11', status: 'Complete', detail: 'Tone: firm · Channel: email.' },
  { id: 6, title: 'Email Sent', time: '09:14:13', status: 'Complete', detail: 'Delivered to finance@abcltd.com.' },
  { id: 7, title: 'Database Updated', time: '09:14:14', status: 'Complete', detail: 'Reminder count → 2 · Last action logged.' },
  { id: 8, title: 'Workflow Complete', time: '09:14:15', status: 'Complete', detail: 'Case remains open until payment.' },
]

export const liveFlow = [
  { id: 1, title: 'User Request', caption: 'Handle INV-1001' },
  { id: 2, title: 'AI Analysis', caption: 'Intent + entities' },
  { id: 3, title: 'Tool Selection', caption: 'Invoice + CRM tools' },
  { id: 4, title: 'Data Retrieval', caption: 'Invoice + history' },
  { id: 5, title: 'Decision', caption: 'Send 2nd reminder' },
  { id: 6, title: 'Action', caption: 'Draft + dispatch email' },
  { id: 7, title: 'Completed', caption: 'Logged in ledger' },
]
