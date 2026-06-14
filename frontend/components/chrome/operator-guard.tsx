"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useRole } from "@/lib/role";

const OPERATOR_ALLOWED_PREFIXES = ["/review"];

function isAllowed(pathname: string): boolean {
  return OPERATOR_ALLOWED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );
}

export function OperatorGuard() {
  const role = useRole();
  const pathname = usePathname() ?? "/";
  const router = useRouter();

  useEffect(() => {
    if (role === "operator" && !isAllowed(pathname)) {
      router.replace("/review");
    }
  }, [role, pathname, router]);

  return null;
}
