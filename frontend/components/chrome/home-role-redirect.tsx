"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";

/**
 * The public landing (`/`) is the customer/visitor home. Operators have no home
 * page — if a signed-in operator lands here (e.g. via the brand logo), send them
 * straight to their review console. Renders nothing.
 */
export function HomeRoleRedirect() {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session?.role === "operator") {
      router.replace("/operator/review-queue");
    }
  }, [session, router]);

  return null;
}
