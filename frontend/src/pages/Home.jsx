import Dashboard from '../components/Dashboard'

export default function Home() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-gray-400 mt-1">
          Live anomaly monitoring · 15-minute pipeline · Causal root cause analysis
        </p>
      </div>
      <Dashboard />
    </div>
  )
}
