// Extracted from App.tsx (pure move, no behaviour change).
import { Component, type ReactNode } from 'react'

// Stops any render error from blanking the whole page.
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="ov" style={{ minHeight: '100vh' }}>
        <div style={{ maxWidth: 520, margin: '0 auto', padding: '96px 24px', textAlign: 'center' }}>
          <div className="ov-eyebrow" style={{ marginBottom: 8 }}>something broke</div>
          <h1 className="ov-h2">The page hit an unexpected error</h1>
          <p style={{ marginTop: 12, fontSize: 14, color: 'var(--body)' }}>
            Your resume and results are safe in your browser. If this started after an update, restart the backend
            (<code style={{ fontFamily: 'var(--font-mono)' }}>python -m src.main serve</code>), then reload.
          </p>
          <button className="ov-btn ov-btn-ink" style={{ marginTop: 20 }} onClick={() => window.location.reload()}>reload</button>
          <pre style={{ marginTop: 20, overflow: 'auto', border: '1px solid var(--rule)', background: 'var(--panel)', padding: 12, textAlign: 'left', fontSize: 11, color: 'var(--dim)' }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
        </div>
      </div>
    )
  }
}
