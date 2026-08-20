"use client";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "./api";

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: dashboardApi.getAll,
    staleTime: 15_000,
  });
}
