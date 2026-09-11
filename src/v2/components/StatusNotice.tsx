import type { ReactNode } from "react";
import { AlertCircle, CheckCircle, InfoCircle } from "@untitledui/icons";
import { Button } from "@/components/base/buttons/button";
import { FeaturedIcon } from "@/components/foundations/featured-icon/featured-icon";
import { cx } from "@/lib/cx";

type NoticeTone = "info" | "success" | "warning" | "error";

type StatusNoticeProps = {
  title: string;
  children: ReactNode;
  tone?: NoticeTone;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
};

const toneStyles: Record<NoticeTone, string> = {
  info: "border-[var(--claros-blue-mist)] bg-[var(--claros-blue-soft)]",
  success: "border-[#b7e1ce] bg-[var(--claros-green-soft)]",
  warning: "border-[#f0d49c] bg-[var(--claros-amber-soft)]",
  error: "border-[#f0c4bf] bg-[#fff5f4]",
};

const toneIcons = {
  info: InfoCircle,
  success: CheckCircle,
  warning: AlertCircle,
  error: AlertCircle,
} as const;

const iconColors = {
  info: "brand",
  success: "success",
  warning: "warning",
  error: "error",
} as const;

export function StatusNotice({
  title,
  children,
  tone = "info",
  actionLabel,
  onAction,
  className,
}: StatusNoticeProps) {
  const Icon = toneIcons[tone];

  return (
    <div
      className={cx(
        "flex w-full items-start gap-3 rounded-xl border p-4 text-left",
        toneStyles[tone],
        className,
      )}
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
    >
      <FeaturedIcon
        icon={Icon}
        color={iconColors[tone]}
        theme="light"
        size="sm"
        className="shrink-0"
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="m-0 text-sm font-semibold text-[var(--claros-ink)]">
          {title}
        </p>
        <div className="mt-1 text-sm leading-6 text-[var(--claros-muted)]">
          {children}
        </div>
        {actionLabel && onAction ? (
          <Button
            color={tone === "error" ? "link-destructive" : "link-color"}
            size="sm"
            onPress={onAction}
            className="mt-2 min-h-11"
          >
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
