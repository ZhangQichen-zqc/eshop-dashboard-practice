import { spawn } from "node:child_process";

const commands = [
  { name: "mall-api", command: "npm", args: ["run", "dev", "--prefix", "server"] },
  {
    name: "dashboard",
    command: "python",
    args: ["-m", "uvicorn", "app.main:app", "--app-dir", "analytics_dashboard", "--host", "127.0.0.1", "--port", "8000", "--reload"]
  }
];

const children = commands.map(({ name, command, args }) => {
  const child = spawn(command, args, {
    stdio: ["ignore", "pipe", "pipe"],
    shell: process.platform === "win32"
  });

  child.stdout.on("data", (data) => process.stdout.write(`[${name}] ${data}`));
  child.stderr.on("data", (data) => process.stderr.write(`[${name}] ${data}`));
  child.on("exit", (code) => {
    if (code && code !== 0) {
      console.error(`[${name}] exited with code ${code}`);
      shutdown();
    }
  });

  return child;
});

function shutdown() {
  for (const child of children) {
    if (!child.killed) child.kill();
  }
}

process.on("SIGINT", () => {
  shutdown();
  process.exit(0);
});

process.on("SIGTERM", () => {
  shutdown();
  process.exit(0);
});
