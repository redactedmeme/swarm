import { NavLink, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { MessageCircle, LayoutDashboard, Bot, Wrench, Settings, LogOut, Hexagon } from 'lucide-react'
import { cn } from '@/app/lib/utils'
import { useAuthStore } from '@/app/store/authStore'

const NAV = [
  { path: '/chat',      icon: MessageCircle,   label: 'Chat' },
  { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/agents',    icon: Bot,             label: 'Agents' },
  { path: '/tools',     icon: Wrench,          label: 'Tools' },
]

export default function Sidebar() {
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <aside className="flex flex-col w-14 shrink-0 border-r border-border bg-card py-3 items-center gap-1">
      {/* Logo */}
      <div className="mb-3 flex items-center justify-center w-9 h-9">
        <motion.div
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
          className="text-primary"
        >
          <Hexagon size={22} strokeWidth={1.5} />
        </motion.div>
      </div>

      <div className="w-7 h-px bg-border mb-2" />

      {/* Nav */}
      <nav className="flex flex-col gap-1 flex-1">
        {NAV.map(({ path, icon: Icon, label }) => (
          <NavLink key={path} to={path} title={label}>
            {({ isActive }) => (
              <span
                className={cn(
                  'flex items-center justify-center w-9 h-9 rounded-lg transition-all duration-150',
                  isActive
                    ? 'bg-primary/15 text-primary glow-sm'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary',
                )}
              >
                <Icon size={18} strokeWidth={1.75} />
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom */}
      <div className="flex flex-col gap-1 items-center">
        <NavLink to="/settings" title="Settings">
          {({ isActive }) => (
            <span
              className={cn(
                'flex items-center justify-center w-9 h-9 rounded-lg transition-all duration-150',
                isActive
                  ? 'bg-primary/15 text-primary'
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary',
              )}
            >
              <Settings size={18} strokeWidth={1.75} />
            </span>
          )}
        </NavLink>
        <button
          onClick={handleLogout}
          title="Logout"
          className="flex items-center justify-center w-9 h-9 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all duration-150"
        >
          <LogOut size={18} strokeWidth={1.75} />
        </button>
      </div>
    </aside>
  )
}
