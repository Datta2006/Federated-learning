import * as React from "react"
import { cn } from "@/lib/utils"

interface SwitchProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
}

const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ className, checked = false, onCheckedChange, ...props }, ref) => {
    const [state, setState] = React.useState(checked)

    const handleChange = () => {
      const newState = !state
      setState(newState)
      onCheckedChange?.(newState)
    }

    return (
      <button
        ref={ref}
        role="switch"
        aria-checked={state}
        onClick={handleChange}
        className={cn(
          "relative inline-flex h-6 w-11 items-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          state
            ? "border-transparent bg-primary text-primary-foreground"
            : "border-input bg-background",
          className
        )}
        {...props}
      >
        <span
          className={cn(
            "inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform",
            state ? "translate-x-5" : "translate-x-1"
          )}
        />
      </button>
    )
  }
)
Switch.displayName = "Switch"

export { Switch }