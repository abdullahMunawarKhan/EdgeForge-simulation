import React from 'react'

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('EDGEFORGE UI Error Boundary caught an error:', error, errorInfo)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
    if (this.props.onReset) {
      this.props.onReset()
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="mx-auto my-12 max-w-2xl rounded-xl border border-danger/30 bg-surface/90 p-8 text-center shadow-panel backdrop-blur-md">
          <div className="inline-flex items-center gap-2 rounded-full border border-danger/30 bg-danger/10 px-3 py-1 text-xs font-mono font-bold text-danger">
            <span className="h-2 w-2 rounded-full bg-danger animate-pulse" />
            EDGEFORGE UI ERROR
          </div>
          <h2 className="mt-4 text-xl font-bold tracking-tight text-text">
            The validation workspace encountered an unexpected rendering error.
          </h2>
          <p className="mt-2 text-xs text-text-muted font-mono bg-bg/80 p-3 rounded border border-border-subtle text-left break-all">
            {this.state.error?.message || 'Component runtime exception'}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <button
              onClick={this.handleReset}
              className="btn btn-primary text-xs font-semibold px-4 py-2"
              type="button"
            >
              RETURN TO OVERVIEW
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
