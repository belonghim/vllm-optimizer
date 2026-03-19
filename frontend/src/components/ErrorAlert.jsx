function ErrorAlert({ message, className }) {
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
