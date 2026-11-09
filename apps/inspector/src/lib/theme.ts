import { useEffect, useState } from "react";

export type ThemeChoice = "system" | "light" | "dark";

const KEY = "openrois-inspector-theme";
const DARK = window.matchMedia?.("(prefers-color-scheme: dark)");

function stored(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

/** Match the browser chrome to the page, as openrois.org does. */
function paintThemeColor(choice: ThemeChoice): void {
  const dark = choice === "dark" || (choice === "system" && Boolean(DARK?.matches));
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0b1017" : "#ffffff");
}

/**
 * The theme the user chose, applied as data-theme on the root element.
 *
 * "system" removes the attribute, so the stylesheet follows prefers-color-scheme.
 */
export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(stored);
  useEffect(() => {
    const root = document.documentElement;
    if (choice === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", choice);
    paintThemeColor(choice);
    try {
      if (choice === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, choice);
    } catch {
      // Storage can be unavailable, in a private window for example. The choice still applies.
    }
    if (choice !== "system" || !DARK) return;
    const follow = () => paintThemeColor("system");
    DARK.addEventListener("change", follow);
    return () => DARK.removeEventListener("change", follow);
  }, [choice]);
  return [choice, setChoice];
}
