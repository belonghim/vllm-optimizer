import { Component } from "react";
import type { ReactNode, ErrorInfo } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" className="error-boundary-container">
          <div className="error-boundary-icon">⚠</div>
          <h2 className="error-boundary-title">
            Something went wrong
          </h2>
          <p className="error-boundary-msg">
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <button
            type="button"
            onClick={() => {
              this.setState({ hasError: false, error: null });
            }}
            className="error-boundary-btn"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
