import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { failed: boolean }

export default class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Diagnostics stay in the local browser console; the student sees no stack,
    // private data, local path, or raw backend payload.
    console.error('NCKH12 UI boundary recovered an unexpected render error.', {
      name: error.name,
      component: info.componentStack?.split('\n').filter(Boolean)[0]?.trim() ?? 'unknown',
    })
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="fatal-boundary" role="alert">
        <p className="kicker">NCKH12 Speaking Coach</p>
        <h1>Something went wrong while opening this result.</h1>
        <p>Your saved recording and assessment have not been changed.</p>
        <div>
          <button className="button primary" onClick={() => window.location.reload()}>Try again</button>
          <a className="button secondary" href="/">Back to Home</a>
        </div>
      </main>
    )
  }
}
