import { Outlet } from 'react-router-dom'
import TopBar from './TopBar.jsx'
import Sidebar from './Sidebar.jsx'

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-950">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <TopBar />
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
