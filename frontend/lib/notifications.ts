"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface Notif {
  id: string;
  variant: "seller" | "buyer" | "system";
  title: string;
  body: string;
  meta_text?: string;
  href?: string;
  created_at: string;
  unread: boolean;
}

export const notifs = {
  async list(): Promise<Notif[]> {
    try {
      const data = await apiFetch<{ notifications: Notif[] }>("/notifications");
      return data.notifications;
    } catch (err: any) {
      if (err.status === 401) return [];
      throw err;
    }
  },

  async markRead(id: string) {
    await apiFetch(`/notifications/${id}/read`, { method: "POST" });
  },

  async markAllRead() {
    await apiFetch("/notifications/read-all", { method: "POST" });
  },
};

export function useNotifs() {
  const query = useQuery({
    queryKey: ["notifications"],
    queryFn: notifs.list,
    refetchInterval: 10000, // Poll every 10 seconds for demo purposes
  });

  return query.data || [];
}

export function useNotifsMutation() {
  const queryClient = useQueryClient();

  const markRead = useMutation({
    mutationFn: notifs.markRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const markAllRead = useMutation({
    mutationFn: notifs.markAllRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  return {
    markRead: markRead.mutateAsync,
    markAllRead: markAllRead.mutateAsync,
  };
}
