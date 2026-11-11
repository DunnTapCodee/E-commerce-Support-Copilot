/**
 * Date & Time utility functions for formatting timestamps in the frontend.
 */

export function parseDateSafe(input?: string | number | Date | null): Date {
  if (!input) return new Date();
  if (input instanceof Date) return input;
  const parsed = new Date(input);
  return isNaN(parsed.getTime()) ? new Date() : parsed;
}

/**
 * Format timestamp as HH:mm (e.g. 14:30)
 */
export function formatSystemTime(input?: string | number | Date | null): string {
  const d = parseDateSafe(input);
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
}

/**
 * Format timestamp as HH:mm:ss (e.g. 14:30:45)
 */
export function formatSystemTimeWithSeconds(input?: string | number | Date | null): string {
  const d = parseDateSafe(input);
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  const seconds = String(d.getSeconds()).padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

/**
 * Format timestamp as YYYY-MM-DD HH:mm:ss or DD/MM/YYYY HH:mm:ss
 */
export function formatSystemDateTime(input?: string | number | Date | null): string {
  const d = parseDateSafe(input);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');
  const seconds = String(d.getSeconds()).padStart(2, '0');
  return `${day}/${month}/${year} ${hours}:${minutes}:${seconds}`;
}

