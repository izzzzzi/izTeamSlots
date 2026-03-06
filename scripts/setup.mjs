#!/usr/bin/env node
/**
 * Cross-platform setup script for izTeamSlots.
 * Delegates to setup.sh (Unix) or setup.cmd (Windows).
 */
import { execFileSync } from "node:child_process";
import { platform } from "node:os";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

if (process.env.IZTEAMSLOTS_SKIP_SETUP === "1") {
  console.log("Skipping setup (IZTEAMSLOTS_SKIP_SETUP=1)");
  process.exit(0);
}

const isWin = platform() === "win32";

try {
  if (isWin) {
    execFileSync("cmd.exe", ["/c", resolve(root, "scripts", "setup.cmd")], {
      stdio: "inherit",
      cwd: root,
    });
  } else {
    execFileSync("bash", [resolve(root, "scripts", "setup.sh")], {
      stdio: "inherit",
      cwd: root,
    });
  }
} catch (err) {
  process.exit(err.status ?? 1);
}
