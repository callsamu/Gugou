const LETTERS: ReadonlyArray<[string, string]> = [
  ["G", "#4285F4"],
  ["u", "#EA4335"],
  ["g", "#FBBC05"],
  ["o", "#4285F4"],
  ["u", "#34A853"],
];

export function Logo({ size = "large" }: { size?: "small" | "large" }) {
  const scale = size === "small" ? "text-4xl" : "text-8xl sm:text-9xl";

  return (
    <div class={`select-none font-semibold tracking-tight ${scale}`} aria-label="Gugou">
      {LETTERS.map(([letter, color]) => (
        <span key={letter} style={{ color }}>
          {letter}
        </span>
      ))}
    </div>
  );
}
