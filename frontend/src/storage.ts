// Settings the browser remembers for this person. Storage can be blocked (private windows,
// cleared site data), so every read and write is allowed to fail: the setting then simply is not
// remembered and the app works as it does on a first visit.
export function readSetting(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeSetting(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // See above.
  }
}
