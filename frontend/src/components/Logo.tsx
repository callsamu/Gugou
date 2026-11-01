const LETTERS: ReadonlyArray<[string, string]> = [
  ["O", "#4285F4"],
  ["B", "#EA4335"],
  ["u", "#FBBC05"],
  ["s", "#4285F4"],
  ["c", "#34A853"],
  ["a", "#EA4335"],
  ["d", "#4285F4"],
  ["o", "#FBBC05"],
  ["r", "#34A853"],
];

export function Logo({ size = "large" }: { size?: "small" | "large" }) {
  const scale = size === "small" ? "text-3xl" : "text-6xl sm:text-7xl";

  return (
    <div class={`select-none font-semibold tracking-tight ${scale}`} aria-label="OBuscador">
      {LETTERS.map(([letter, color]) => (
        <span key={letter} style={{ color }}>
          {letter}
        </span>
      ))}
    </div>
  );
}
