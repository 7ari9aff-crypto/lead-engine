import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-200 disabled:pointer-events-none disabled:opacity-50 select-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] active:scale-[0.98] shadow-sm",
        secondary:
          "bg-[var(--bg-soft)] text-[var(--fg)] border border-[var(--border)] hover:bg-[var(--bg-hover)] hover:border-[var(--border)]",
        ghost: "text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg-hover)]",
        outline:
          "border border-[var(--border)] text-[var(--fg)] hover:bg-[var(--bg-hover)] hover:border-[var(--accent)]",
        danger:
          "bg-[var(--danger)] text-white hover:opacity-90 active:scale-[0.98]",
        success:
          "bg-[var(--success)] text-white hover:opacity-90 active:scale-[0.98]",
        gradient:
          "text-white shadow-md bg-[image:var(--gradient)] hover:opacity-95 active:scale-[0.98]",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-4",
        lg: "h-11 px-6 text-base",
        icon: "h-9 w-9",
        "icon-sm": "h-8 w-8",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, loading, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size }), className)}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading && (
          <span className="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
        )}
        {children}
      </Comp>
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
