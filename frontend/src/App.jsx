import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Home    from './pages/Home'
import Reports from './pages/Reports'

const nav = 'px-4 py-2 rounded text-sm font-medium hover:bg-teal-light transition-colors'
const active = 'bg-teal-light text-teal font-semibold'

export default function App() {
  return (
    <BrowserRouter>
      <header className="bg-[#1E7A78] text-white px-6 py-3 flex items-center justify-between shadow-md">
        <span className="text-xl font-black tracking-widest">KAIROS</span>
        <nav className="flex gap-2">
          <NavLink to="/"       end className={({ isActive }) => `${nav} ${isActive ? active : 'text-white/80'}`}>Dashboard</NavLink>
          <NavLink to="/reports"    className={({ isActive }) => `${nav} ${isActive ? active : 'text-white/80'}`}>Reports</NavLink>
        </nav>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/"        element={<Home />} />
          <Route path="/reports" element={<Reports />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
