import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"

import { cn } from "@/lib/utils"

function Tabs({ className, ...props }: TabsPrimitive.Root.Props) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function TabsList({ className, ...props }: TabsPrimitive.List.Props) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "relative inline-flex h-9 w-fit items-center gap-0.5 rounded-lg bg-secondary p-[3px] text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function TabsTab({ className, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-tab"
      className={cn(
        "relative z-10 inline-flex h-full items-center justify-center gap-1.5 rounded-[calc(var(--radius-lg)-3px)] px-3 text-[13px] font-medium whitespace-nowrap text-muted-foreground transition-colors outline-none select-none focus-visible:ring-2 focus-visible:ring-ring data-active:text-foreground disabled:pointer-events-none disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

function TabsIndicator({ className, ...props }: TabsPrimitive.Indicator.Props) {
  return (
    <TabsPrimitive.Indicator
      data-slot="tabs-indicator"
      className={cn(
        "absolute top-1/2 left-0 z-0 h-[calc(100%-6px)] w-(--active-tab-width) -translate-y-1/2 translate-x-(--active-tab-left) rounded-[calc(var(--radius-lg)-3px)] bg-card shadow-sm transition-all duration-200 ease-[var(--ease-brand)]",
        className
      )}
      {...props}
    />
  )
}

function TabsPanel({ className, ...props }: TabsPrimitive.Panel.Props) {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-panel"
      className={cn("outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsIndicator, TabsList, TabsPanel, TabsTab }
