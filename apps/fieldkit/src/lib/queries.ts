import { useQuery } from "@tanstack/react-query";
import { getSwarm, getToken } from "@/lib/swarm";

export function useSwarm() {
  return useQuery({
    queryKey: ["swarm"],
    queryFn: () => getSwarm(),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useToken() {
  return useQuery({
    queryKey: ["token"],
    queryFn: () => getToken(),
    staleTime: 12_000,
    refetchInterval: 20_000,
  });
}
