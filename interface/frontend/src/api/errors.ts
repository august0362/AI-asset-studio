import type { ErrorCode, ErrorItem, ErrorResponse } from "./types";
export function issue(
  code: ErrorCode,
  field: string | null,
  message: string,
  severity: "error" | "warning" = "error",
  details: Record<string, unknown> = {},
  retryable = false,
): ErrorItem {
  return { code, severity, field, message, details, retryable };
}
export class ApiError extends Error {
  constructor(
    public readonly response: ErrorResponse,
    public readonly status = 422,
  ) {
    super(response.errors.map((e) => e.message).join(" "));
    this.name = "ApiError";
  }
}
export function reject(code: ErrorCode, message: string, status = 404, field: string | null = null): never {
  throw new ApiError(
    {
      contract_version: "1.0",
      errors: [issue(code, field, message)],
      warnings: [],
    },
    status,
  );
}
export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "The request failed. Try again.";
}
