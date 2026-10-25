import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import Navbar from './Navbar'

function Layout() {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const isSettingsPage = location.pathname.startsWith('/settings')

  return (
    <div className="min-h-screen">
      {!isSettingsPage && (
        <Sidebar open={open} onClose={() => setOpen(false)} />
      )}
      <div className={isSettingsPage ? '' : 'lg:pl-60'}>
        <Navbar onMenu={() => setOpen(true)} isSettingsPage={isSettingsPage} />
        <main className={isSettingsPage ? 'max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8' : 'px-4 py-6 sm:px-6 lg:px-8'}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default Layout
