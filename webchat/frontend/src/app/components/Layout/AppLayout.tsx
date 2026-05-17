import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function AppLayout() {
  return (
    <div className="flex flex-col-reverse md:flex-row h-dvh w-full overflow-hidden bg-background">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
