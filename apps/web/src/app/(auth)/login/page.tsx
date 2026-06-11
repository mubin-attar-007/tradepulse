import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

// LoginForm reads `?next=` via useSearchParams, so it must sit under Suspense
// for the static shell of this page to prerender without a CSR bailout.
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
