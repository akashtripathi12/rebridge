import { redirect } from "next/navigation";

/** Legacy /returns → /returns/handle. The operator-facing return flow. */
export default function ReturnsRedirect() {
  redirect("/returns/handle");
}
