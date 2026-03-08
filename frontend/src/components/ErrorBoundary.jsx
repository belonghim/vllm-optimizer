import { Component } from "react";
import { COLORS, font } from "../constants";

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 48, textAlign: "center",
          fontFamily: font.mono, color: COLORS.text,
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠</div>
          <h2 style={{ color: COLORS.red, marginBottom: 8 }}>
            Something went wrong
          </h2>
          <p style={{ color: COLORS.muted, marginBottom: 24, maxWidth: 480, margin: "0 auto 24px" }}>
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
            }}
            style={{
              background: COLORS.accent, color: COLORS.bg,
              border: "none", padding: "8px 24px", cursor: "pointer",
              fontFamily: font.mono, fontWeight: 700, fontSize: 13,
            }}
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
