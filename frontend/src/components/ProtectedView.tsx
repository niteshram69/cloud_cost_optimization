"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { PageState } from "@/components/PageState";
import { useAuth } from "@/hooks/useAuth";
import type { UserRole } from "@/lib/types";

interface ProtectedViewProps {
  children: React.ReactNode;
  requiredRole?: UserRole;
}

export function ProtectedView({ children, requiredRole }: ProtectedViewProps) {
  const router = useRouter();
  const { initialized, token, user } = useAuth();

  useEffect(() => {
    if (!initialized) return;

    if (!token) {
      router.replace("/login");
      return;
    }

    if (requiredRole && user?.role !== requiredRole) {
      router.replace("/dashboard");
    }
  }, [initialized, requiredRole, router, token, user?.role]);

  if (!initialized) {
    return <PageState title="Loading session" message="Validating credentials..." />;
  }

  if (!token) {
    return <PageState title="Redirecting" message="Please sign in to continue." />;
  }

  if (requiredRole && user?.role !== requiredRole) {
    return <PageState title="Access restricted" message="Admin role is required." />;
  }

  return <>{children}</>;
}
