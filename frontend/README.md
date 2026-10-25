# AI-Powered Autonomous Accounts Receivable Management Agent

A professional, enterprise-grade fintech SaaS dashboard built for a Final Year Engineering Project demonstration. This application showcases an AI-powered Accounts Receivable (AR) management agent that automates invoice collection workflows, customer risk profiling, and payment tracking.

---

## Features

### Core Pages
1. **Dashboard** — Overview of key financial KPIs with real-time agent status and recent activity feed.
2. **Invoices** — Complete invoice tracking table with filters, status badges, and detail modal.
3. **Customers** — Customer directory with risk scoring, payment behavior profiles, and industry tags.
4. **Agent Chat** — ChatGPT-style interface to interact with the autonomous AR collection agent.
5. **Agent Activity** — Visual workflow timeline and step-by-step reasoning trace of the agent's execution.

### UI/UX Highlights
- **Light / Dark Theme System** — Smooth transitions with CSS variables, persisted via `localStorage`.
- **Professional Enterprise Design** — Clean card-based SaaS layout with subtle shadows and consistent spacing.
- **Finance KPI Cards** — Total Invoices, Pending Payments, Collection Rate, Average Days Outstanding.
- **Sticky Header Tables** — Scrollable tables with hover effects, status badges, and action columns.
- **Sidebar Navigation** — Minimal, icon-driven menu with active state highlighting.
- **Micro Interactions** — Subtle card hover lift, button scale effects, and smooth color transitions.
- **Responsive Layout** — Works on mobile, tablet, and desktop screens.

---

## Tech Stack

| Category       | Technology                              |
|----------------|-----------------------------------------|
| Framework      | React 19                                |
| Build Tool     | Vite 8                                  |
| Styling        | Tailwind CSS 3 (with CSS Variables)     |
| Routing        | React Router 7                          |
| Icons          | Lucide React                            |
| Font           | Inter (Google Fonts)                    |

No complex animation libraries — all transitions use native CSS for simplicity and performance.

---

## Theme System

The application ships with a fully-featured Light/Dark mode toggle:

- **Toggle Location** — Moon / Sun button in the top-right corner of the navbar.
- **Persistence** — Theme choice is saved to `localStorage` under the key `theme`.
- **System Preference** — First-time visitors default to their OS-level color scheme preference.
- **Smooth Transitions** — All color changes animate over 250ms for a polished feel.

### Light Theme
| Element     | Color      |
|-------------|------------|
| Background  | `#F8FAFC`  |
| Cards       | `#FFFFFF`  |
| Text        | `#0F172A`  |
| Borders     | `#E2E8F0`  |

### Dark Theme
| Element     | Color      |
|-------------|------------|
| Background  | `#0F172A`  |
| Cards       | `#1E293B`  |
| Text        | `#F8FAFC`  |
| Borders     | `#334155`  |

---

## Design Specifications

### Border Radius
- Cards: `12px`
- Buttons: `10px`
- Inputs: `10px`

### Typography (Inter Font)
- Headings: `700` (Bold)
- Body: `400` (Regular)
- Small labels: `500` (Medium)

### Status Badge Colors
| Status     | Color          |
|------------|----------------|
| Pending    | Amber / Orange |
| Paid       | Green          |
| Overdue    | Red            |
| Processing | Blue           |

### Button Styles
| Variant  | Appearance                          |
|----------|-------------------------------------|
| Primary  | Dark blue background, white text    |
| Secondary| Border-only, transparent background |
| Danger   | Red background, white text          |

All buttons include a subtle scale animation on hover (`1.02x`) and active press (`0.98x`).

---

## Project Structure

```
src/
├── assets/           # Static images and SVGs
├── components/       # Reusable UI components
│   ├── Layout.jsx    # Main app shell (sidebar + navbar + outlet)
│   ├── Navbar.jsx    # Top bar with search, theme toggle, user avatar
│   └── Sidebar.jsx   # Left navigation menu
├── data/             # Dummy data files (no backend)
│   ├── activities.js # Dashboard recent activity + agent stats
│   ├── chat.js       # Agent chat conversations + messages
│   ├── customers.js  # Customer list with risk profiles
│   ├── invoices.js   # Invoice records with status/aging
│   └── workflow.js   # Agent workflow visualization data
├── hooks/            # Custom React hooks
│   └── ThemeContext.jsx  # Theme provider + localStorage
├── pages/            # Route-level pages
│   ├── Dashboard.jsx
│   ├── Invoices.jsx
│   ├── Customers.jsx
│   ├── AgentChat.jsx
│   └── AgentActivity.jsx
├── App.jsx           # Router configuration
├── main.jsx          # Entry point (wraps app with ThemeProvider)
└── index.css         # CSS variables + component classes
```

---

## Getting Started

### Prerequisites
- Node.js (v16 or newer)
- npm (bundled with Node.js)

### Installation

```bash
# 1. Install dependencies
npm install

# 2. Start the development server
npm run dev
```

Vite will print a local URL (typically `http://localhost:5173`) — open it in your browser.

### Other Scripts

```bash
# Build for production
npm run build

# Preview the production build locally
npm run preview

# Run the linter (Oxlint)
npm run lint
```

---

## Data Model (Dummy)

The demo uses realistic hardcoded data across 5 modules:

- **~50 Customers** — Each with industry, email, risk score (Low/Medium/High), and payment status.
- **~100 Invoices** — Each with ID, customer, amount, due date, status (Paid/Pending/Overdue), and aging days.
- **Agent Activity Feed** — Recent events (overdue detected, reminder sent, payment received, escalation, promise-to-pay).
- **Agent Stats** — Session-level counters (processed, reminders, escalations, collected amount).
- **Workflow Timeline** — 6-step reasoning trace (Analysis → Tool Selection → DB Query → Decision → Email → Update).

All data is static — there is no backend, API, or database. The project is designed as a pure frontend demonstration.

---

## Project Context

This application was developed as a Final Year Engineering Project submission to demonstrate the concept of an **AI-powered Autonomous Accounts Receivable Agent**. The UI is designed to look and feel like a real fintech SaaS product (similar to Stripe, Linear, or Notion dashboards), suitable for live demos and exhibition showcases.

### Intended Use
- Classroom presentation / defense demo
- Project exhibition display
- UI/UX reference for enterprise dashboard design

---

## Customization Tips

All colors and design tokens are centralized in two places — tweak once, apply everywhere:

1. **`src/index.css`** — CSS variables (`:root` for Light, `.dark` for Dark) and reusable component classes.
2. **`tailwind.config.js`** — Tailwind extensions (shadows, border radius, colors).

To add a new page:
1. Create a new file under `src/pages/NewPage.jsx`
2. Add a route in `src/App.jsx`
3. Add a menu entry in `src/components/Sidebar.jsx`

---

## License

This is a student academic project. For demonstration purposes only.
