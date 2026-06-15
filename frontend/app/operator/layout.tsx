import { RoleRouteGuard } from "@/components/chrome/role-route-guard";

/**
 * Operator route group (`/operator/*`) — the returns/grading/review back office.
 * Only operator sessions get past the guard; customers are bounced to their own
 * marketplace landing and signed-out visitors to /login.
 */
export default function OperatorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <RoleRouteGuard allow="operator">{children}</RoleRouteGuard>;
}
