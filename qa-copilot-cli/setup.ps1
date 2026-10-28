# Registers QA MCP servers with GitHub Copilot CLI and VS Code, and installs the qa-analyst agent.
# Safe to re-run. Credentials stay in rag/.env and are never passed to Copilot's config.
$ErrorActionPreference = "Stop"

$cliRoot  = $PSScriptRoot
$repoRoot = Split-Path $cliRoot -Parent
$python   = Join-Path $repoRoot ".venv\Scripts\python.exe"
$server   = Join-Path $cliRoot "mcp_server.py"
$agentSrc = Join-Path $repoRoot ".github\agents\qa-analyst.agent.md"
$skillsDir = Join-Path $repoRoot ".github\skills"

if (-not (Test-Path $python)) { throw "Python venv not found at $python. Run .\setup.ps1 from the repository root first." }
if (-not (Test-Path $agentSrc)) { throw "QA analyst agent not found at $agentSrc." }
$nodeCandidates = @()
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeCandidates += (Get-Command node).Source
}
if ($env:NVM_HOME -and (Test-Path $env:NVM_HOME)) {
    foreach ($versionDir in Get-ChildItem $env:NVM_HOME -Directory -ErrorAction SilentlyContinue) {
        $candidate = Join-Path $versionDir.FullName "node.exe"
        if (Test-Path $candidate) { $nodeCandidates += $candidate }
    }
}
$compatibleNode = $null
$compatibleVersion = [version]"0.0"
foreach ($candidate in ($nodeCandidates | Select-Object -Unique)) {
    try {
        $versionText = (& $candidate --version 2>$null).Trim().TrimStart('v')
        $version = [version]$versionText
        if ($version.Major -ge 22 -and $version -gt $compatibleVersion) {
            $compatibleNode = $candidate
            $compatibleVersion = $version
        }
    } catch { }
}
if (-not $compatibleNode) { throw "Playwright MCP requires Node.js 22 or later. Install/activate a supported Node version first." }
$nodeHome = Split-Path $compatibleNode -Parent
$npxCli = Join-Path $nodeHome "node_modules\npm\bin\npx-cli.js"
if (-not (Test-Path $npxCli)) { throw "npm's npx-cli.js was not found under $nodeHome." }
$allowedOrigins = if ($env:PLAYWRIGHT_ALLOWED_ORIGINS) { $env:PLAYWRIGHT_ALLOWED_ORIGINS } else { "https://e2etest.pilyr.com;https://arontier.pilyr.com;https://assets.pilyr.com;https://cdn.jsdelivr.net;https://cdnjs.cloudflare.com" }
foreach ($skill in @("jira-analysis", "manual-test-design", "test-case-generation", "test-case-review", "duplicate-test-detection", "cypress-automation-generation", "cypress-notes-automation", "cypress-archive-content-type-automation")) {
    if (-not (Test-Path (Join-Path $skillsDir "$skill\SKILL.md"))) {
        throw "Required Copilot skill '$skill' is missing from $skillsDir."
    }
}

$copilotHome = if ($env:COPILOT_HOME) { $env:COPILOT_HOME } else { Join-Path $HOME ".copilot" }
$agentDir = Join-Path $copilotHome "agents"
New-Item -ItemType Directory -Force -Path $agentDir | Out-Null
Copy-Item $agentSrc (Join-Path $agentDir "qa-analyst.agent.md") -Force
Write-Host "Installed agent: $agentDir\qa-analyst.agent.md"
Write-Host "Validated repository skills: $skillsDir"

# Edit mcp-config.json directly: the VS Code 'copilot' shim exits 0 even when the real CLI is missing.
$configPath = Join-Path $copilotHome "mcp-config.json"
$config = if (Test-Path $configPath) { Get-Content $configPath -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
if (-not $config.PSObject.Properties["mcpServers"]) {
    $config | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
}
$entry = [pscustomobject]@{
    type    = "local"
    command = $python
    args    = @($server)
    env     = [pscustomobject]@{ PYTHONIOENCODING = "utf-8" }
    tools   = @("*")
}
$config.mcpServers | Add-Member -NotePropertyName "qa-hub" -NotePropertyValue $entry -Force
$playwrightEntry = [pscustomobject]@{
    type    = "local"
    command = $compatibleNode
    args    = @($npxCli, "--yes", "@playwright/mcp@0.0.82", "--isolated", "--allowed-origins", $allowedOrigins)
    env     = [pscustomobject]@{ PATH = "$nodeHome;$env:PATH" }
    tools   = @("*")
}
$config.mcpServers | Add-Member -NotePropertyName "playwright" -NotePropertyValue $playwrightEntry -Force
if (Test-Path $configPath) { Copy-Item $configPath "$configPath.bak" -Force }
# UTF-8 without BOM; Windows PowerShell's -Encoding UTF8 adds a BOM that JSON parsers may reject.
[System.IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding($false)))

$check = (Get-Content $configPath -Raw | ConvertFrom-Json).mcpServers."qa-hub"
if (-not $check -or $check.command -ne $python) { throw "Verification failed: qa-hub not found in $configPath." }
$playwrightCheck = (Get-Content $configPath -Raw | ConvertFrom-Json).mcpServers."playwright"
if (-not $playwrightCheck -or $playwrightCheck.command -ne $compatibleNode) { throw "Verification failed: Playwright MCP not found in $configPath." }
Write-Host "Registered MCP servers 'qa-hub' and 'playwright' in $configPath"
Write-Host "Playwright MCP Node runtime: v$compatibleVersion; allowed origins: $allowedOrigins"

# Register the same servers in VS Code's user profile for regular Copilot Chat.
# Preserve existing servers and inputs, replacing only these two named entries.
$vscodeMcpPath = Join-Path $env:APPDATA "Code\User\mcp.json"
$vscodeConfig = if (Test-Path $vscodeMcpPath) {
    Get-Content $vscodeMcpPath -Raw | ConvertFrom-Json
} else {
    [pscustomobject]@{}
}
if (-not $vscodeConfig.PSObject.Properties["servers"]) {
    $vscodeConfig | Add-Member -NotePropertyName servers -NotePropertyValue ([pscustomobject]@{})
}
$vscodeConfig.servers | Add-Member -NotePropertyName "qa-hub" -NotePropertyValue ([pscustomobject]@{
    type    = "stdio"
    command = $python
    args    = @($server)
    env     = [pscustomobject]@{ PYTHONIOENCODING = "utf-8" }
}) -Force
$vscodeConfig.servers | Add-Member -NotePropertyName "playwright" -NotePropertyValue ([pscustomobject]@{
    type    = "stdio"
    command = $compatibleNode
    args    = @($npxCli, "--yes", "@playwright/mcp@0.0.82", "--isolated", "--allowed-origins", $allowedOrigins)
    env     = [pscustomobject]@{ PATH = "$nodeHome;$env:PATH" }
}) -Force
if (Test-Path $vscodeMcpPath) { Copy-Item $vscodeMcpPath "$vscodeMcpPath.bak" -Force }
[System.IO.File]::WriteAllText(
    $vscodeMcpPath,
    ($vscodeConfig | ConvertTo-Json -Depth 20),
    (New-Object System.Text.UTF8Encoding($false))
)
$vscodeCheck = Get-Content $vscodeMcpPath -Raw | ConvertFrom-Json
if (-not $vscodeCheck.servers."qa-hub" -or -not $vscodeCheck.servers.playwright) {
    throw "Verification failed: qa-hub or playwright not found in VS Code MCP config $vscodeMcpPath."
}
Write-Host "Registered MCP servers 'qa-hub' and 'playwright' in VS Code profile $vscodeMcpPath"

$cliOk = $false
# Skip the VS Code shim: it prompts interactively and can trigger a global npm install.
$realCli = Get-Command copilot -All -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -and $_.Source -notmatch 'globalStorage\\github\.copilot-chat' } |
    Select-Object -First 1
if ($realCli) {
    try { $null = & $realCli.Source --version 2>$null; $cliOk = ($LASTEXITCODE -eq 0) } catch { }
}
if ($cliOk) {
    Write-Host "`nDone. Start with:  copilot --agent=qa-analyst"
} else {
    Write-Warning "Registration is complete, but a working GitHub Copilot CLI was not detected. Install it (requires a current Node.js LTS), then run:  copilot --agent=qa-analyst"
}
