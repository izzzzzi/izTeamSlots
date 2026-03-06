#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { platform } from "node:os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");
const isWin = platform() === "win32";

// Resolve Python from venv
const venvPython = isWin
  ? resolve(root, ".venv", "Scripts", "python.exe")
  : resolve(root, ".venv", "bin", "python");

if (existsSync(venvPython)) {
  process.env.PYTHON_BIN = venvPython;
}

// Find bun
let bunCmd = "bun";
if (isWin) {
  const userBun = resolve(process.env.USERPROFILE || "", ".bun", "bin", "bun.exe");
  if (existsSync(userBun)) bunCmd = userBun;
} else {
  const homeBun = resolve(process.env.HOME || "", ".bun", "bin", "bun");
  if (existsSync(homeBun)) bunCmd = homeBun;
}

const args = ["run", "--cwd", resolve(root, "ui"), "src/main.ts", ...process.argv.slice(2)];

try {
  execFileSync(bunCmd, args, { stdio: "inherit", cwd: root, env: process.env, shell: isWin });
} catch (err) {
  process.exit(err.status ?? 1);
}
