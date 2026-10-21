import { api } from '../api'
import AlertFeed from '../components/AlertFeed'
import { useAction, useApi } from '../hooks'
import { Empty, ErrorBanner, PageHeader, Spinner } from '../components/ui'

export default function Reports({ status }) {
  const latest = useApi('/report/latest')
  const alerts = useApi('/alerts/history', { interval: 30_000 })
  const gen = useAction()
  const test = useAction()
  const report = latest.data
  const text = report?.report || report?.text

  async function generate() {
    const r = await gen.run(async () => (await api.post('/report', null, { params: { hours: 24 } })).data)
    if (r) latest.setData(r)
  }
  async function sendTest() {
    const r = await test.run(async () => (await api.post('/alerts/test')).data)
    if (r) alerts.reload()
  }

  const channels = alerts.data?.channels ?? status?.channels ?? {}

  return (
    <div className="space-y-6">
      <PageHeader title="Reports & Alerts"
        subtitle="Plain-English executive reports. Every number is checked against the data by the LLM-Modulo verifier before it is sent.">
        <button className="btn-primary" onClick={generate} disabled={gen.busy}>
          {gen.busy ? <><Spinner /> Writing report…</> : 'Generate report'}
        </button>
      </PageHeader>
      <ErrorBanner error={gen.error || test.error} />

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card lg:col-span-2">
          <div className="card-h">
            <span className="font-semibold text-sm">Executive report</span>
            {report && text && (
              <div className="flex gap-2">
                {report.verified
                  ? <span className="chip bg-emerald-50 text-emerald-700" title="All numbers and metric names match the data">✓ LLM-Modulo verified</span>
                  : <span className="chip bg-red-50 text-red-700">unverified</span>}
                <span className="chip bg-gray-100 text-gray-600">{report.engine}</span>
                {report.attempts > 1 && <span className="chip bg-amber-50 text-amber-700">{report.attempts} attempts</span>}
              </div>
            )}
          </div>
          <div className="p-6">
            {text
              ? <p className="text-[15px] leading-7 whitespace-pre-line text-gray-800">{text}</p>
              : <Empty>Click <b>Generate report</b> to summarise the last 24 hours of anomalies and their causes.</Empty>}
            {report?.issues?.length > 0 && (
              <div className="mt-5 rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
                <b>The LLM draft was rejected by the verifier</b> and replaced with a grounded template:
                <ul className="list-disc ml-5 mt-1">{report.issues.map((i, k) => <li key={k}>{i}</li>)}</ul>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-5">
            <div className="font-semibold text-sm mb-3">Delivery channels</div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span>Telegram</span>{channels.telegram ? <span className="text-emerald-600 font-semibold">configured</span> : <span className="text-gray-400">not set</span>}</div>
              <div className="flex justify-between"><span>Email (Gmail SMTP)</span>{channels.email ? <span className="text-emerald-600 font-semibold">configured</span> : <span className="text-gray-400">not set</span>}</div>
              <div className="flex justify-between"><span>Dashboard</span><span className="text-emerald-600 font-semibold">always</span></div>
            </div>
            <button className="btn-ghost w-full mt-4" onClick={sendTest} disabled={test.busy}>{test.busy ? <Spinner /> : 'Send test alert'}</button>
          </div>
          <div className="card p-5 text-xs text-gray-500 leading-relaxed">
            <div className="font-semibold text-sm text-gray-800 mb-2">How alerting avoids spam</div>
            Alerts fire only for anomalies seen for the <b>first time</b>, within the last 24 h of data, at or above the minimum
            severity, and not for a metric already alerted within the cooldown window (<code>KAIROS_ALERT_COOLDOWN_MIN</code>).
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-h"><span className="font-semibold text-sm">Alert history</span></div>
        <div className="p-5"><AlertFeed history={alerts.data?.history} /></div>
      </div>
    </div>
  )
}
