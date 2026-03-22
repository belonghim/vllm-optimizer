interface ErrorAlertProps {
  message: string | null;
  className?: string;
}

function ErrorAlert({ message, className }: ErrorAlertProps) {
  if (!message) return null;
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`error-alert${className ? ` ${className}` : ""}`}
    >
      ⚠ {message}
    </div>
  );
}

export default ErrorAlert;
