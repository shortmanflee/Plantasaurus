import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";

export const useLocationTree = () =>
  useQuery({ queryKey: ["locations", "tree"], queryFn: () => unwrap(api.GET("/api/v1/locations/tree")) });

export const useCustomFields = (entity: "plant" | "instance" | "area" | "spot") =>
  useQuery({
    queryKey: ["custom-fields", entity],
    queryFn: () => unwrap(api.GET("/api/v1/custom-fields", { params: { query: { entity } } })),
    staleTime: 60_000,
  });

export const useAuthStatus = () =>
  useQuery({ queryKey: ["auth"], queryFn: () => unwrap(api.GET("/api/v1/auth/status")), staleTime: 60_000 });

export const usePlantOptions = () =>
  useQuery({
    queryKey: ["plants", "options"],
    queryFn: () => unwrap(api.GET("/api/v1/plants", { params: { query: { limit: 500 } } })),
    select: (page) => page.items.map((p) => ({ value: String(p.id), label: p.common_name })),
  });

export const useHAStatus = () =>
  useQuery({
    queryKey: ["homeassistant", "status"],
    queryFn: () => unwrap(api.GET("/api/v1/homeassistant/status")),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });

export const useOPBStatus = () =>
  useQuery({
    queryKey: ["opb", "status"],
    queryFn: () => unwrap(api.GET("/api/v1/openplantbook/status")),
    staleTime: 60_000,
  });

export const useMCPStatus = () =>
  useQuery({
    queryKey: ["mcp", "status"],
    queryFn: () => unwrap(api.GET("/api/v1/mcp/status")),
    staleTime: 60_000,
  });

export const useHAIssues =(enabled = true) =>
  useQuery({
    queryKey: ["homeassistant", "issues"],
    queryFn: () => unwrap(api.GET("/api/v1/homeassistant/issues")),
    enabled,
    staleTime: 60_000,
  });

export type HARole = "irrigation_zone" | "plant_monitor";

/** Labelled HA devices for a role. Fetching re-syncs with HA so newly added devices appear. */
export const useHADevices = (role: HARole, enabled = true) =>
  useQuery({
    queryKey: ["homeassistant", "devices", role],
    queryFn: () => unwrap(api.GET("/api/v1/homeassistant/devices", { params: { query: { role } } })),
    enabled,
    staleTime: 30_000,
  });
