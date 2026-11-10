import { notifications } from "@mantine/notifications";
import { QueryKey, useMutation, useQueryClient } from "@tanstack/react-query";

interface Options<TData> {
  invalidate?: QueryKey[];
  success?: string | ((data: TData) => string);
  onSuccess?: (data: TData) => void;
}

/** useMutation with standard cache invalidation and success/error toasts. */
export function useApiMutation<TVars, TData = unknown>(
  fn: (vars: TVars) => Promise<TData>,
  { invalidate = [], success, onSuccess }: Options<TData> = {},
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (data) => {
      await Promise.all(invalidate.map((key) => qc.invalidateQueries({ queryKey: key })));
      if (success) {
        notifications.show({ color: "green", message: typeof success === "function" ? success(data) : success });
      }
      onSuccess?.(data);
    },
    onError: (err: Error) => {
      notifications.show({ color: "red", title: "Something went wrong", message: err.message });
    },
  });
}
