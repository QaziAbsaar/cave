import { ReactNode } from "react";

type Status = "pending" | "running" | "success" | "failed" | "intervention_needed";

interface StatusBadgeProps {
  status: Status;
  children?: ReactNode;
}

const STATUS_CLASSES: Record<Status, string> = {
  pending: "status-pending",
  running: "status-running",
  success: "status-success",
  failed: "status-failed",
  intervention_needed: "status-intervention",
};

const STATUS_LABELS: Record<Status, string> = {
  pending: "Pending",
  running: "Running",
  success: "Success",
  failed: "Failed",
  intervention_needed: "Needs Review",
};

export function StatusBadge({ status, children }: StatusBadgeProps) {
  const base =
    "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wider";
  const classes = STATUS_CLASSES[status] || STATUS_CLASSES.pending;

  return (
    <span className={`${base} ${classes}`}>
      <span className="w-1.5 h-1.5 rounded-full currentColor" />
      {children || STATUS_LABELS[status]}
    </span>
  );
}
