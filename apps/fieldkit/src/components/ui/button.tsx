import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "@radix-ui/react-slot";
import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-sans font-semibold uppercase tracking-wider transition-[opacity,transform,background-color,border-color,color] duration-[var(--motion-quick)] ease-[var(--ease-out)] disabled:pointer-events-none disabled:opacity-40 active:not-disabled:scale-[0.96] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg",
  {
    variants: {
      variant: {
        primary:
          "bg-fg text-bg border border-fg hover:opacity-90",
        ghost:
          "bg-transparent text-fg border border-border-2 hover:border-fg",
        subtle:
          "bg-bg-3 text-muted border border-border hover:text-fg hover:border-border-2",
        warn:
          "bg-transparent text-warn border border-warn/40 hover:border-warn",
      },
      size: {
        sm: "h-9 px-3 text-2xs rounded-sm",
        md: "h-11 px-4 text-xs rounded-sm",
        lg: "h-12 px-5 text-xs rounded-md",
        icon: "size-11 rounded-sm",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({
  className,
  variant,
  size,
  asChild,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}
