export function value(
  input: unknown,
  fallback = "Not available",
): string {
  if (input === null || input === undefined || input === "") {
    return fallback;
  }
  return String(input);
}


export function sourceValue(input: unknown): string {
  return value(input, "Not reported by statewide source");
}


export function numberValue(
  input: unknown,
  digits = 2,
): string {
  if (typeof input !== "number") {
    return "Not available";
  }
  return input.toLocaleString(undefined, {
    maximumFractionDigits: digits,
  });
}


export function score(input: unknown): string {
  return typeof input === "number"
    ? `${Math.round(input * 100)}%`
    : "Not available";
}


export function distance(input: unknown): string {
  if (typeof input !== "number") {
    return "Not available";
  }
  return input >= 1000
    ? `${(input / 1000).toFixed(2)} km`
    : `${Math.round(input)} m`;
}


export function percentage(input: unknown): string {
  return typeof input === "number"
    ? `${(input * 100).toFixed(1)}%`
    : "Not available";
}
