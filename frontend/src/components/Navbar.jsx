import { useNavigate, useLocation } from 'react-router-dom'
import { Menu, Moon, Settings, Sun, LogOut } from 'lucide-react'
import { useTheme } from '../hooks/ThemeContext'
import logoImg from '../assets/logo.png'

function Navbar({ onMenu, isSettingsPage = false }) {
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    alert('Logout functionality will be enabled when authentication is active.')
  }

  const getPageMeta = (pathname) => {
    if (pathname === '/') {
      return {
        title: 'Accounts Receivable Overview',
        subtitle: 'Real-time portfolio monitoring & automated credit control',
      }
    }
    if (pathname.startsWith('/invoices')) {
      return {
        title: 'Invoice Portfolio',
        subtitle: 'Receivables tracking, accrued penalties & reminder workflows',
      }
    }
    if (pathname.startsWith('/customers')) {
      return {
        title: 'Corporate Customer Directory',
        subtitle: 'Debtor risk profiling, credit scoring & account management',
      }
    }
    if (pathname.startsWith('/approvals')) {
      return {
        title: 'Executive Approval Gateway',
        subtitle: 'Review & authorize high-value proposals, escalations & reminders',
      }
    }
    if (pathname.startsWith('/chat')) {
      return {
        title: 'Autonomous AR Intelligence',
        subtitle: 'Conversational portfolio queries, reasoning & debtor actions',
      }
    }
    if (pathname.startsWith('/activity')) {
      return {
        title: 'Executive Action & Audit Ledger',
        subtitle: 'Real-time history of automated decisions & ledger validations',
      }
    }
    if (pathname.startsWith('/settings')) {
      return {
        title: 'Admin Settings',
        subtitle: 'Penalty rules, reminders cadence, bank details & agent controls',
      }
    }
    return {
      title: 'Accounts Receivable Management',
      subtitle: 'Autonomous credit control platform',
    }
  }

  const pageMeta = getPageMeta(location.pathname)

  return (
    <header className="navbar">
      <div className={`flex items-center gap-3 sm:gap-4 px-4 py-3.5 sm:py-4 sm:px-7 min-h-[72px] sm:min-h-[78px] ${isSettingsPage ? 'max-w-7xl mx-auto w-full' : ''}`}>
        {isSettingsPage ? (
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-3.5 hover:opacity-85 transition-opacity mr-2 cursor-pointer"
            title="Return to Dashboard"
          >
            <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-xl bg-white dark:bg-slate-800 shadow-xs border border-slate-200/90 dark:border-slate-700/80 p-1 flex items-center justify-center shrink-0">
              <img
                src={logoImg}
                alt="ReceivIQ Logo"
                className="h-full w-full object-contain"
              />
            </div>
            <span
              className="text-xl sm:text-[22px] font-bold tracking-tight font-sans hidden sm:inline-block"
              style={{ color: 'var(--text)' }}
            >
              ReceivIQ
            </span>
          </button>
        ) : (
          <button
            className="icon-btn lg:hidden shrink-0"
            onClick={onMenu}
            aria-label="Open menu"
          >
            <Menu size={18} />
          </button>
        )}

        {/* Dynamic Page Title in Header: displayed for all pages except settings page */}
        {!isSettingsPage && (
          <div className="flex flex-col min-w-0 mr-auto pl-1 sm:pl-3 py-0.5 justify-center">
            <h1
              className="text-base sm:text-lg md:text-xl font-bold tracking-tight truncate leading-snug"
              style={{ color: 'var(--text)' }}
            >
              {pageMeta.title}
            </h1>
            <p
              className="text-xs sm:text-[13px] truncate hidden sm:block mt-0.5 font-normal"
              style={{ color: 'var(--text-muted)' }}
            >
              {pageMeta.subtitle}
            </p>
          </div>
        )}

        <div className="ml-auto flex items-center gap-2.5 sm:gap-3 shrink-0">
          {/* Theme Toggle Button with Icon and Name */}
          <button
            onClick={toggleTheme}
            className="flex items-center justify-center gap-2 px-3.5 sm:px-4 py-2 text-xs sm:text-sm font-semibold rounded-btn border transition-all duration-150 shadow-xs hover:border-border-hover hover:scale-[1.02] cursor-pointer min-w-[110px]"
            style={{
              borderColor: 'var(--border)',
              background: 'var(--card)',
              color: 'var(--text)',
            }}
            aria-label={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
            title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
          >
            {theme === 'light' ? (
              <>
                <Moon size={16} className="text-primary shrink-0" />
                <span>Dark Mode</span>
              </>
            ) : (
              <>
                <Sun size={16} className="text-amber-400 shrink-0" />
                <span>Light Mode</span>
              </>
            )}
          </button>

          {/* Admin Settings Button with Icon and Name */}
          <button
            onClick={() => navigate('/settings')}
            className={`flex items-center justify-center gap-2 px-3.5 sm:px-4 py-2 text-xs sm:text-sm font-semibold rounded-btn border transition-all duration-150 shadow-xs hover:scale-[1.02] cursor-pointer min-w-[100px] ${
              isSettingsPage
                ? 'text-primary bg-primary/10 border-primary/40 font-bold'
                : 'hover:border-border-hover'
            }`}
            style={{
              borderColor: isSettingsPage ? undefined : 'var(--border)',
              background: isSettingsPage ? undefined : 'var(--card)',
              color: isSettingsPage ? 'var(--primary)' : 'var(--text)',
            }}
            aria-label="Admin Settings"
            title="Admin Settings"
          >
            <Settings size={16} className={`shrink-0 ${isSettingsPage ? 'text-primary animate-spin-slow' : 'text-text-muted'}`} />
            <span>Settings</span>
          </button>

          {/* Profile Card & Logout button in Navbar: rendered for Settings page */}
          {isSettingsPage && (
            <div className="flex items-center gap-2.5 pl-3 border-l" style={{ borderColor: 'var(--border)' }}>
              <div
                className="flex items-center gap-2.5 rounded-card border py-1.5 pl-1.5 pr-3 shadow-xs"
                style={{ borderColor: 'var(--border)', background: 'var(--card-secondary)' }}
              >
                <div className="avatar font-bold">AG</div>
                <div className="hidden sm:block">
                  <p className="text-sm font-semibold leading-tight" style={{ color: 'var(--text)' }}>
                    Ashish Gokani
                  </p>
                  <p className="text-[11px] font-medium" style={{ color: 'var(--text-muted)' }}>
                    Admin
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="icon-btn hover:text-danger hover:border-danger/30 transition-colors cursor-pointer"
                title="Log out"
                aria-label="Log out"
              >
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

export default Navbar
