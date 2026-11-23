/**
 * Date & Time utility functions for formatting timestamps in the frontend.
 * Standard display timezone: Asia/Ho_Chi_Minh (UTC+07:00).
 */

export interface DateParseOptions {
  /**
   * Legacy SQLite CURRENT_TIMESTAMP rows (e.g. telemetry_logs) are naive UTC strings
   * without a timezone suffix. Set true to interpret naive strings as UTC before
   * converting to Asia/Ho_Chi_Minh. Leave false for legacy wall-clock strings.
   */
  assumeUtcForNaive?: boolean;
}

const HAS_EXPLICIT_TZ_RE = /(?:Z|[+-]\d{2}:?\d{2})$/i;
const NAIVE_DATETIME_RE = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?)$/;

function formatPartsInVietnam(d: Date): {
  year: string;
  month: string;
  day: string;
  hours: string;
  minutes: string;
  seconds: string;
} {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(d);

  const map: Record<string, string> = {};
  for (const p of parts) {
    if (p.type !== 'literal') {
      map[p.type] = p.value;
    }
  }
  return {
    year: map.year || '1970',
    month: map.month || '01',
    day: map.day || '01',
    hours: map.hour === '24' ? '00' : map.hour || '00',
    minutes: map.minute || '00',
    seconds: map.second || '00',
  };
}

export function parseDateSafe(
  input?: string | number | Date | null,
  options?: DateParseOptions
): Date {
  if (!input) return new Date();
  if (input instanceof Date) return input;
  if (typeof input === 'number') return new Date(input);

  const trimmed = input.trim();
  if (!trimmed) return new Date();

  if (HAS_EXPLICIT_TZ_RE.test(trimmed)) {
    const parsed = new Date(trimmed);
    return isNaN(parsed.getTime()) ? new Date() : parsed;
  }

  const naiveMatch = NAIVE_DATETIME_RE.exec(trimmed);
  if (naiveMatch) {
    const isoCore = `${naiveMatch[1]}T${naiveMatch[2]}`;
    const withTz = options?.assumeUtcForNaive ? `${isoCore}Z` : `${isoCore}+07:00`;
    const parsed = new Date(withTz);
    return isNaN(parsed.getTime()) ? new Date() : parsed;
  }

  const parsed = new Date(trimmed);
  return isNaN(parsed.getTime()) ? new Date() : parsed;
}

/**
 * Format timestamp as HH:mm in Asia/Ho_Chi_Minh (e.g. 14:30)
 */
export function formatSystemTime(
  input?: string | number | Date | null,
  options?: DateParseOptions
): string {
  const d = parseDateSafe(input, options);
  const { hours, minutes } = formatPartsInVietnam(d);
  return `${hours}:${minutes}`;
}

/**
 * Format timestamp as HH:mm:ss in Asia/Ho_Chi_Minh (e.g. 14:30:45)
 */
export function formatSystemTimeWithSeconds(
  input?: string | number | Date | null,
  options?: DateParseOptions
): string {
  const d = parseDateSafe(input, options);
  const { hours, minutes, seconds } = formatPartsInVietnam(d);
  return `${hours}:${minutes}:${seconds}`;
}

/**
 * Format timestamp as DD/MM/YYYY HH:mm:ss in Asia/Ho_Chi_Minh
 */
export function formatSystemDateTime(
  input?: string | number | Date | null,
  options?: DateParseOptions
): string {
  const d = parseDateSafe(input, options);
  const { year, month, day, hours, minutes, seconds } = formatPartsInVietnam(d);
  return `${day}/${month}/${year} ${hours}:${minutes}:${seconds}`;
}
