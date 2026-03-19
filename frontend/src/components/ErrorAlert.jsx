function ErrorAlert({ message, className }) {
  if (!message) return null;
  return (
    <div className={`error-alert${className ? ` ${className}` : ""}`}>
      ⚠ {message}
    </div>
  );
}

export default ErrorAlert;
