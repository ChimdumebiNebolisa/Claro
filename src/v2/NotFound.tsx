import { Link } from "react-router-dom";
import { Brand } from "./Brand";

export default function NotFound() {
  return (
    <main className="v2-not-found">
      <Brand />
      <h1>That page is not available.</h1>
      <p>
        The address may have changed, or this worksheet may no longer be
        available.
      </p>
      <Link className="v2-primary-link" to="/">
        Return home
      </Link>
    </main>
  );
}
