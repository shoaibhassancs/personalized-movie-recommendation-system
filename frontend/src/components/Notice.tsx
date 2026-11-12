import type { ReactNode } from "react";

export function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="notice notice-error">
      {children}
    </p>
  );
}

export function InfoNotice({ children }: { children: ReactNode }) {
  return <p className="notice notice-info">{children}</p>;
}
