import Dashboard from '../components/Dashboard'
import { PageHeader } from '../components/ui'

export default function Home({ status }) {
  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle="KAIROS watches every connected metric, detects anomalies, finds their causal origin and alerts you — without being asked."
      />
      <Dashboard status={status} />
    </div>
  )
}
