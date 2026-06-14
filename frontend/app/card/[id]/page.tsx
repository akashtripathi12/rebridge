import { redirect } from "next/navigation";

export default function LegacyCardRedirect({ params }: { params: { id: string } }) {
  redirect(`/product/${params.id}`);
}
