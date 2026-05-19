param(
    [string]$ApiUrl = "http://127.0.0.1:8000",
    [int]$EmbeddingWaitSeconds = 240,
    [int]$ExtractionWaitSeconds = 60
)

$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "================================================================================"
    Write-Host $Title
    Write-Host "================================================================================"
}

function Write-CommandLine {
    param([string]$Exe, [string[]]$Arguments)
    Write-Host ("> " + $Exe + " " + ($Arguments -join " "))
}

function Invoke-RawExe {
    param(
        [string]$Label,
        [string]$Exe,
        [string[]]$Arguments
    )
    Write-Section $Label
    Write-CommandLine -Exe $Exe -Arguments $Arguments
    & $Exe @Arguments
    Write-Host "EXIT_CODE=$LASTEXITCODE"
}

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw ".env not found at $Path"
    }
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) { return }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) { return }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Invoke-NexusJson {
    param([string[]]$Arguments)
    $output = & $script:Nexus @Arguments 2>&1 | Out-String
    Write-Host $output
    if ($LASTEXITCODE -ne 0) {
        Write-Host "EXIT_CODE=$LASTEXITCODE"
        return $null
    }
    try {
        return $output | ConvertFrom-Json
    }
    catch {
        Write-Host "JSON_PARSE_EXCEPTION: $($_.Exception.Message)"
        return $null
    }
}

function Invoke-RawRestJson {
    param(
        [string]$Label,
        [string]$Method,
        [string]$Uri,
        [object]$Body = $null
    )
    Write-Section $Label
    Write-Host "> $Method $Uri"
    if ($null -ne $Body) {
        Write-Host "REQUEST_BODY:"
        Write-Host ($Body | ConvertTo-Json -Depth 10)
    }
    try {
        $reqArgs = @{ Method = $Method; Uri = $Uri; ContentType = "application/json" }
        if ($null -ne $Body) { $reqArgs.Body = ($Body | ConvertTo-Json -Depth 10) }
        $response = Invoke-RestMethod @reqArgs
        Write-Host "RESPONSE:"
        Write-Host ($response | ConvertTo-Json -Depth 20)
        return $response
    }
    catch {
        Write-Host "REST_EXCEPTION: $($_.Exception.Message)"
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
        return $null
    }
}

function Wait-ForEmbedded {
    param([int]$TimeoutSeconds)
    Write-Section "POLL: waiting for at least one embedded document"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0
    while ((Get-Date) -lt $deadline) {
        $attempt++
        Write-Host "POLL_ATTEMPT=$attempt"
        $snapshot = Invoke-NexusJson -Arguments @("status", "--json")
        if ($null -ne $snapshot) {
            $embedded = 0
            $fetched = 0
            $chunked = 0
            if ($snapshot.docs_by_status.PSObject.Properties.Name -contains "embedded") {
                $embedded = [int]$snapshot.docs_by_status.embedded
            }
            if ($snapshot.docs_by_status.PSObject.Properties.Name -contains "fetched") {
                $fetched = [int]$snapshot.docs_by_status.fetched
            }
            if ($snapshot.docs_by_status.PSObject.Properties.Name -contains "chunked") {
                $chunked = [int]$snapshot.docs_by_status.chunked
            }
            Write-Host "EMBEDDED=$embedded  FETCHED=$fetched  CHUNKED=$chunked"
            if ($embedded -ge 1 -and $fetched -eq 0 -and $chunked -eq 0) {
                Write-Host "POLL_RESULT=pipeline_settled"
                return
            }
        }
        Start-Sleep -Seconds 5
    }
    Write-Host "POLL_RESULT=timeout"
}

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$script:Nexus = Join-Path $RepoRoot ".venv\Scripts\nexus.exe"

if (-not (Test-Path -LiteralPath $Python)) { throw "Missing venv Python: $Python" }
if (-not (Test-Path -LiteralPath $script:Nexus)) { throw "Missing Nexus CLI: $script:Nexus" }

Import-DotEnv -Path (Join-Path $RepoRoot ".env")

Write-Section "RUN CONTEXT"
Write-Host "TIMESTAMP=$((Get-Date).ToString('o'))"
Write-Host "REPO_ROOT=$RepoRoot"
Write-Host "API_URL=$ApiUrl"
Write-Host "DATABASE_URL=$env:DATABASE_URL"

# ---------------------------------------------------------------------------
# API health check
# ---------------------------------------------------------------------------

Write-Section "API HEALTH"
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "$ApiUrl/health" -TimeoutSec 10).Content
}
catch {
    throw "API is not reachable at $ApiUrl : $($_.Exception.Message)"
}

# ---------------------------------------------------------------------------
# DB reset
# ---------------------------------------------------------------------------

Invoke-RawExe -Label "BEFORE RESET: nexus status" -Exe $script:Nexus -Arguments @("status")

Write-Section "RESET: truncate Nexus data tables"
$resetCode = @'
import asyncio, os
from sqlalchemy import text
from app.db.session import make_engine

async def main():
    engine = make_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                TRUNCATE TABLE
                    claim_evidence, claims, brief_items, briefs,
                    agent_runs, spans, documents, sources
                RESTART IDENTITY CASCADE
            """))
    finally:
        await engine.dispose()
    print("RESET_OK")

asyncio.run(main())
'@
$ResetPy = Join-Path ([System.IO.Path]::GetTempPath()) ("nexus-reset-" + [Guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $ResetPy -Value $resetCode -Encoding UTF8
& $Python $ResetPy
if ($LASTEXITCODE -ne 0) { throw "Database reset failed" }

Invoke-RawExe -Label "AFTER RESET: nexus status --json" -Exe $script:Nexus -Arguments @("status", "--json")

# ---------------------------------------------------------------------------
# Seed a text document
# ---------------------------------------------------------------------------

$FixtureDir = Join-Path ([System.IO.Path]::GetTempPath()) ("nexus-phase3-validation-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $FixtureDir | Out-Null

$fixtureFile = Join-Path $FixtureDir "phase3-fixture.md"
Set-Content -LiteralPath $fixtureFile -Encoding UTF8 -Value @"
# Phase 3 Validation Fixture

OpenAI released GPT-5 in early 2026, achieving a significant improvement in benchmark scores compared to GPT-4.
The model was tested on MMLU, HumanEval, and MATH, with scores of 95.2%, 91.5%, and 88.7% respectively.
DeepMind's Gemini Ultra 2 also surpassed GPT-4 on most benchmarks but scored below GPT-5 on reasoning tasks.
Anthropic announced Claude 4 Opus with improved instruction following and reduced hallucination rates.
Several open-source models including Llama 4 and Mistral Large 3 were released under permissive licenses.
These releases mark a new phase in the competitive landscape of large language models.
"@

Write-Host "FIXTURE_FILE=$fixtureFile"

Invoke-RawExe `
    -Label "INGEST TEXT: Phase 3 Fixture" `
    -Exe $script:Nexus `
    -Arguments @(
        "ingest", "text",
        "--title", "Phase 3 Validation — LLM Releases 2026",
        "--file", $fixtureFile,
        "--source-name", "validation_phase3",
        "--domain-pack", "personal_ai_tech",
        "--json"
    )

# ---------------------------------------------------------------------------
# Wait for pipeline to embed the document
# ---------------------------------------------------------------------------

Wait-ForEmbedded -TimeoutSeconds $EmbeddingWaitSeconds

# ---------------------------------------------------------------------------
# Get the document ID
# ---------------------------------------------------------------------------

Write-Section "FETCH: get embedded document ID"
$docs = Invoke-NexusJson -Arguments @("documents", "--status", "embedded", "--json", "--limit", "1")
if ($null -eq $docs -or @($docs).Count -eq 0) {
    throw "No embedded document found after pipeline settled"
}
$docId = @($docs)[0].id
Write-Host "DOC_ID=$docId"

# ---------------------------------------------------------------------------
# Phase 3 extraction tests
# ---------------------------------------------------------------------------

Write-Section "TEST 1: nexus extract <doc_id> (first run — should succeed)"
$summary = Invoke-NexusJson -Arguments @(
    "extract", $docId,
    "--api-url", $ApiUrl,
    "--json"
)
if ($null -eq $summary) {
    Write-Host "EXTRACT_RESULT=FAILED (null response)"
}
else {
    Write-Host "CLAIMS_EXTRACTED=$($summary.claims_extracted)"
    Write-Host "SPANS_PROCESSED=$($summary.spans_processed)"
    Write-Host "TOKENS_USED=$($summary.tokens_used)"
    Write-Host "COST_USD=$($summary.cost_estimate_usd)"
    if ($summary.claims_extracted -gt 0) {
        Write-Host "EXTRACT_RESULT=PASS"
    }
    else {
        Write-Host "EXTRACT_RESULT=WARN_NO_CLAIMS"
    }
}

Write-Section "TEST 2: nexus document <doc_id> --claims (inline claims view)"
Invoke-RawExe `
    -Label "nexus document --claims" `
    -Exe $script:Nexus `
    -Arguments @("document", $docId, "--claims", "--db-url", $env:DATABASE_URL)

Write-Section "TEST 3: nexus extract <doc_id> without --force (should get 409)"
$output409 = & $script:Nexus "extract" $docId "--api-url" $ApiUrl 2>&1 | Out-String
$exit409 = $LASTEXITCODE
Write-Host $output409
Write-Host "EXIT_CODE=$exit409"
if ($exit409 -ne 0 -and ($output409 -match "409" -or $output409 -match "already exist")) {
    Write-Host "409_TEST=PASS (non-zero exit AND 409 message — re-run blocked as expected)"
}
else {
    Write-Host "409_TEST=FAIL (expected non-zero exit WITH 409 message; exit=$exit409 message_match=$($output409 -match '409|already exist'))"
}

Write-Section "TEST 4: nexus extract <doc_id> --force (re-extraction)"
$summaryForce = Invoke-NexusJson -Arguments @(
    "extract", $docId, "--force",
    "--api-url", $ApiUrl,
    "--json"
)
if ($null -ne $summaryForce) {
    Write-Host "FORCE_CLAIMS_EXTRACTED=$($summaryForce.claims_extracted)"
    Write-Host "FORCE_EXTRACT_RESULT=PASS"
}
else {
    Write-Host "FORCE_EXTRACT_RESULT=FAILED"
}

Write-Section "TEST 5: nexus document --claims --json (JSON round-trip)"
$docWithClaims = Invoke-NexusJson -Arguments @(
    "document", $docId, "--claims", "--json",
    "--db-url", $env:DATABASE_URL
)
if ($null -ne $docWithClaims -and $docWithClaims.PSObject.Properties.Name -contains "claims") {
    Write-Host "JSON_CLAIMS_COUNT=$(@($docWithClaims.claims).Count)"
    Write-Host "JSON_CLAIMS_TEST=PASS"
}
else {
    Write-Host "JSON_CLAIMS_TEST=FAIL (claims key missing)"
}

# ---------------------------------------------------------------------------
# Final status
# ---------------------------------------------------------------------------

Invoke-RawExe -Label "FINAL: nexus status" -Exe $script:Nexus -Arguments @("status")
Invoke-RawExe -Label "FINAL: nexus status --json" -Exe $script:Nexus -Arguments @("status", "--json")

Write-Section "SCRIPT COMPLETE"
Write-Host "TIMESTAMP=$((Get-Date).ToString('o'))"
Write-Host "DOC_ID=$docId"
Write-Host "FIXTURE_DIR=$FixtureDir"
