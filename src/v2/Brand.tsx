import { Link } from "react-router-dom";

export function Brand({ to = "/" }: { to?: string }) {
  return (
    <Link className="claros-brand" to={to} aria-label="Claros home">
      <span className="claros-brand-mark" aria-hidden="true">
        C
      </span>
      <span>Claros</span>
    </Link>
  );
}
