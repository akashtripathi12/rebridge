"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Button — restyled to v2 tokens (NOT default shadcn). Primary action is
 * confident BLACK (Nike CTA); amber is never a button fill in app chrome.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 font-sans font-bold rounded-pill transition-transform duration-150 ease-out hover:-translate-y-0.5 active:translate-y-0 disabled:pointer-events-none disabled:opacity-100 focus-visible:outline-2 focus-visible:outline-offset-2",
  {
    variants: {
      variant: {
        primary: "bg-ink text-white shadow-md",
        secondary: "bg-white text-ink border border-hair hover:bg-paper",
        ghost: "bg-transparent text-mute hover:text-ink hover:-translate-y-0",
        amber: "bg-amber text-ink shadow-md", // hero only; reserved
        // The disabled "not ready yet" state of the reveal CTA.
        idle: "bg-hair text-stone cursor-not-allowed hover:translate-y-0",
      },
      size: {
        md: "px-6 py-3.5 text-[15px]",
        sm: "px-4 py-2.5 text-[13px]",
        lg: "px-7 py-4 text-[15px]",
        block: "w-full px-4 py-4 text-[15px]",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { buttonVariants };
