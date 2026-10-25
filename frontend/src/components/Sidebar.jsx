import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  FileText,
  Users,
  MessageSquare,
  Activity,
  UserCheck,
  Sparkles,
  X,
  LogOut,
} from 'lucide-react'

import logoImg from '../assets/logo.png'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/invoices', label: 'Invoices', icon: FileText },
  { to: '/customers', label: 'Customers', icon: Users },
  { to: '/approvals', label: 'Approvals', icon: UserCheck },
  { to: '/chat', label: 'Agent Chat', icon: MessageSquare },
  { to: '/activity', label: 'Agent Activity', icon: Activity },
]

function Sidebar({ open, onClose }) {
  const handleLogout = () => {
    alert('Logout functionality will be enabled when authentication is active.')
  }

  return (
    <>
      {open && (
        <div className="overlay" onClick={onClose} />
      )}

      <aside
        className={`sidebar w-60 ${
          open ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
      >
        <div className="flex items-center justify-between px-5 sm:px-6 h-20 sm:h-[84px] shrink-0">
          <div className="flex items-center gap-3.5">
            <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-xl bg-white dark:bg-slate-800 shadow-xs border border-slate-200/90 dark:border-slate-700/80 p-1 flex items-center justify-center shrink-0">
              <img
                src={logoImg}
                alt="ReceivIQ Logo"
                className="h-full w-full object-contain"
              />
            </div>
            <span
              className="text-xl sm:text-[22px] font-bold tracking-tight font-sans"
              style={{ color: 'var(--text)' }}
            >
              ReceivIQ
            </span>
          </div>
          <button className="icon-btn-ghost h-8 w-8 lg:hidden" onClick={onClose} aria-label="Close menu">
            <X size={16} />
          </button>
        </div>

        <nav className="mt-1 flex-1 space-y-1 px-3 overflow-y-auto">
          {links.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={onClose}
                className={({ isActive }) =>
                  `sidebar-link ${isActive ? 'active' : ''}`
                }
              >
                <span className="sidebar-icon">
                  <Icon size={16} />
                </span>
                <span>{item.label}</span>
              </NavLink>
            )
          })}
        </nav>

        {/* User Profile Card & Logout Action */}
        <div className="p-3 border-t mt-auto" style={{ borderColor: 'var(--sidebar-border)' }}>
          <div
            className="flex items-center justify-between gap-2 rounded-card border p-2 shadow-xs"
            style={{ borderColor: 'var(--border)', background: 'var(--card-secondary)' }}
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="avatar shrink-0 font-bold">AG</div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold leading-tight truncate" style={{ color: 'var(--text)' }}>
                  Ashish Gokani
                </p>
                <p className="text-[11px] truncate font-medium" style={{ color: 'var(--text-muted)' }}>
                  Admin
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="icon-btn-ghost h-8 w-8 shrink-0 hover:text-danger hover:bg-danger/10 transition-colors"
              title="Log out"
              aria-label="Log out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}

export default Sidebar
