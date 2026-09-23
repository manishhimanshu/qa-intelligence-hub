import { runCli } from "@uarlouski/testrail-mcp-server/dist/cli.js";

const code = await runCli(process.argv.slice(2));
process.exitCode = code;
