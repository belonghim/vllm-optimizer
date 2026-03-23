interface ErrorAlertProps {
  message: string | null;
  className?: string;
  severity?: "error" | "warning";
}

function ErrorAlert({ message, className, severity = "error" }: ErrorAlertProps) {
  if (!message) return null;
  
  const severityClass = severity === "warning" ? " error-alert--warning" : "";
  
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`error-alert${severityClass}${className ? ` ${className}` : ""}`}
    >
      ⚠ {message}
    </div>
  );
}

export default ErrorAlert;
