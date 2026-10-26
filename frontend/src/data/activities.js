// Dummy feed used on the Dashboard recent activity card
export const recentActivities = [
  {
    id: 1,
    title: 'Invoice INV-1001 overdue',
    detail: 'ABC Ltd crossed the 18-day aging threshold.',
    time: '2 min ago',
    type: 'overdue',
  },
  {
    id: 2,
    title: 'Reminder sent to ABC Ltd',
    detail: 'Second reminder drafted and dispatched.',
    time: '8 min ago',
    type: 'reminder',
  },
  {
    id: 3,
    title: 'Payment received from XYZ Ltd',
    detail: 'INV-1002 settled for $8,250.',
    time: '24 min ago',
    type: 'payment',
  },
  {
    id: 4,
    title: 'Customer escalated for review',
    detail: 'Helios Retail flagged as high risk.',
    time: '1 hr ago',
    type: 'escalate',
  },
  {
    id: 5,
    title: 'Promise-to-pay captured',
    detail: 'NovaTech committed to pay by 21 Oct.',
    time: '3 hr ago',
    type: 'promise',
  },
]

export const agentStats = [
  { label: 'Invoices Processed', value: '148', hint: 'Today' },
  { label: 'Reminders Generated', value: '36', hint: 'Today' },
  { label: 'Cases Escalated', value: '07', hint: 'Needs review' },
  { label: 'Payments Collected', value: '$84.2k', hint: 'This week' },
]
