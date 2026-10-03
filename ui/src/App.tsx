import { NavLink, Route, Routes } from 'react-router-dom'
import { useRun } from './api/hooks'
import { formatDate } from './domain/format'
import { About } from './screens/About'
import { BeforeAfter } from './screens/BeforeAfter'
import { FieldView } from './screens/FieldView'
import { Overview } from './screens/Overview'

const navCls = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-2.5 py-1.5 text-sm font-medium ${isActive ? 'bg-stone-900 text-white' : 'text-stone-700 hover:bg-stone-200'}`

export default function App() {
  const run = useRun()
  return (
    <div className="flex h-full flex-col">
      <header className="no-print flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-stone-200 bg-white px-4 py-2">
        <NavLink to="/" className="text-base font-semibold tracking-tight">
          Seggerde soil
        </NavLink>
        <nav className="flex gap-1">
          <NavLink to="/" end className={navCls}>
            Farm
          </NavLink>
          <NavLink to="/demo/before-after" className={navCls}>
            Before / After
          </NavLink>
          <NavLink to="/about" className={navCls}>
            About the data
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-2 text-xs text-stone-500">
          {run.data && <span>Data as of {formatDate(run.data.data_as_of.sentinel2)}</span>}
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto lg:overflow-hidden">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/field/:plotId/:tab?" element={<FieldView />} />
          <Route path="/demo/before-after/:plotId?" element={<BeforeAfter />} />
          <Route path="/about" element={<About />} />
        </Routes>
      </main>
    </div>
  )
}
