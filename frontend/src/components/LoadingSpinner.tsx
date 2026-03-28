export default function LoadingSpinner() {
  return (
    <div className="loading-spinner" role="status" aria-label="Loading">
      <span className="loading-spinner__dot" />
      <span className="loading-spinner__dot" />
      <span className="loading-spinner__dot" />
    </div>
  );
}
