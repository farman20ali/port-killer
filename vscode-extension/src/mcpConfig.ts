import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

export interface McpServerEntry {
  type?: string;
  command: string;
  args?: string[];
  env?: Record<string, string>;
}

export interface McpConfigFile {
  servers?: Record<string, McpServerEntry>;
  mcpServers?: Record<string, McpServerEntry>;
}

function getWorkspaceMcpPath(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    return undefined;
  }
  return path.join(folders[0].uri.fsPath, ".vscode", "mcp.json");
}

function readJsonFile(filePath: string): McpConfigFile {
  if (!fs.existsSync(filePath)) {
    return {};
  }
  const raw = fs.readFileSync(filePath, "utf8");
  return JSON.parse(raw) as McpConfigFile;
}

function writeJsonFile(filePath: string, data: McpConfigFile): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + "\n", "utf8");
}

export function buildKportMcpEntry(
  executable: string,
  useLegacyArgs: boolean
): McpServerEntry {
  return {
    type: "stdio",
    command: executable,
    args: useLegacyArgs ? ["--mcp"] : ["mcp"],
  };
}

export async function configureWorkspaceMcp(
  executable: string,
  useLegacyArgs: boolean
): Promise<string | undefined> {
  const mcpPath = getWorkspaceMcpPath();
  if (!mcpPath) {
    return undefined;
  }

  const config = readJsonFile(mcpPath);
  const entry = buildKportMcpEntry(executable, useLegacyArgs);

  if (config.servers) {
    config.servers.kport = entry;
  } else if (config.mcpServers) {
    config.mcpServers.kport = entry;
  } else {
    config.servers = { kport: entry };
  }

  writeJsonFile(mcpPath, config);
  return mcpPath;
}

export async function maybeAutoConfigureMcp(): Promise<void> {
  const cfg = vscode.workspace.getConfiguration("kport");
  if (!cfg.get<boolean>("mcp.autoConfigure")) {
    return;
  }

  const executable = cfg.get<string>("executablePath", "kport");
  const useLegacyArgs = cfg.get<boolean>("mcp.useLegacyArgs", false);
  const mcpPath = await configureWorkspaceMcp(executable, useLegacyArgs);
  if (mcpPath) {
    void vscode.window.showInformationMessage(
      `KPort MCP server registered in ${path.basename(path.dirname(mcpPath))}/mcp.json`
    );
  }
}
