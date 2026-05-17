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
    <aside className={cn(
      'shrink-0 border-border bg-card',
      // Mobile: horizontal bottom bar
      'flex flex-row w-full h-14 border-t items-center justify-around px-2',
      // Desktop: vertical left sidebar
      'md:flex-col md:w-14 md:h-full md:border-t-0 md:border-r md:py-3 md:px-0 md:items-center md:justify-start md:gap-1',
    )}>
      {/* Logo — desktop only */}
      <div className="hidden md:flex mb-3 items-center justify-center w-9 h-9">
        <motion.div
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
          className="text-primary"
        >
          <Hexagon size={22} strokeWidth={1.5} />
        </motion.div>
      </div>

      <div className="hidden md:block w-7 h-px bg-border mb-2" />

      {/* Nav */}
      <nav className="flex flex-row md:flex-col gap-1 md:flex-1 items-center">
        {NAV.map(({ path, icon: Icon, label }) => (
          <NavLink key={path} to={path} title={label}>
            {({ isActive }) => (
              <span
                className={cn(
                  'flex items-center justify-center w-10 h-10 md:w-9 md:h-9 rounded-lg transition-all duration-150',
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

      {/* Settings + Logout */}
      <div className="flex flex-row md:flex-col gap-1 items-center">
        <NavLink to="/settings" title="Settings">
          {({ isActive }) => (
            <span
              className={cn(
                'flex items-center justify-center w-10 h-10 md:w-9 md:h-9 rounded-lg transition-all duration-150',
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
          className="flex items-center justify-center w-10 h-10 md:w-9 md:h-9 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all duration-150"
        >
          <LogOut size={18} strokeWidth={1.75} />
        </button>
      </div>
    </aside>
  )
}
