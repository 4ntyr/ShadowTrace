import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeName = "dark" | "light";

/** Chart tokens. Categorical/sequential/status values are the validated reference palette,
 *  stepped separately for each surface (dark is selected, not inverted). */
export interface ChartTokens {
  surface: string;
  text: string;
  textSecondary: string;
  muted: string;
  grid: string;
  axis: string;
  categorical: string[];
  sequential: string[]; // low → high
  divergingNeg: string;
  divergingPos: string;
  neutral: string;
  cyber: string;
  kinetic: string;
  status: { good: string; warning: string; serious: string; critical: string };
}

const DARK: ChartTokens = {
  surface: "#1a1a19",
  text: "#f0efec",
  textSecondary: "#c3c2b7",
  muted: "#8f8e86",
  grid: "#2c2c2a",
  axis: "#4a4a45",
  categorical: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"],
  // On dark, "near zero" recedes into the dark surface: dark steps → light steps.
  sequential: ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf", "#2a78d6", "#3987e5", "#5598e7", "#86b6ef"],
  divergingNeg: "#e66767",
  divergingPos: "#3987e5",
  neutral: "#383835",
  cyber: "#3987e5",
  kinetic: "#d95926",
  status: { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" },
};

const LIGHT: ChartTokens = {
  surface: "#fcfcfb",
  text: "#0b0b0b",
  textSecondary: "#52514e",
  muted: "#6f6e68",
  grid: "#e6e5e0",
  axis: "#c3c2b7",
  categorical: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
  sequential: ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#1c5cab"],
  divergingNeg: "#e34948",
  divergingPos: "#2a78d6",
  neutral: "#f0efec",
  cyber: "#2a78d6",
  kinetic: "#eb6834",
  status: { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" },
};

/** Colour follows the entity, never its rank: each sponsoring state owns a fixed slot.
 *  Anything else folds into neutral "Other". */
export const STATE_SLOTS: Record<string, number> = { RU: 7, CN: 3, IR: 2, KP: 4, US: 0, IL: 6, UA: 1, BY: 5 };

interface Ctx { theme: ThemeName; setTheme: (t: ThemeName) => void; tokens: ChartTokens }
const ThemeCtx = createContext<Ctx>({ theme: "dark", setTheme: () => {}, tokens: DARK });

function initialTheme(): ThemeName {
  try {
    const saved = localStorage.getItem("st-theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch { /* storage unavailable */ }
  return "dark";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeName>(initialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("st-theme", theme); } catch { /* ignore */ }
  }, [theme]);
  const value = useMemo(() => ({ theme, setTheme, tokens: theme === "dark" ? DARK : LIGHT }), [theme]);
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export const useTheme = () => useContext(ThemeCtx);

export function stateColor(tokens: ChartTokens, code: string | null | undefined): string {
  if (code && code in STATE_SLOTS) return tokens.categorical[STATE_SLOTS[code]];
  return tokens.muted;
}
