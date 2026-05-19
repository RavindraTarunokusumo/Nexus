param(
    [string]$ApiUrl = "http://127.0.0.1:8000",
    [int]$EmbeddingWaitSeconds = 240,
    [switch]$SkipRss
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
    $code = $LASTEXITCODE
    Write-Host "EXIT_CODE=$code"
}

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw ".env not found at $Path"
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) {
            return
        }

        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
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
    Write-Host ("> $Method $Uri")
    if ($null -ne $Body) {
        Write-Host "REQUEST_BODY:"
        Write-Host ($Body | ConvertTo-Json -Depth 10)
    }

    try {
        $args = @{
            Method = $Method
            Uri = $Uri
            ContentType = "application/json"
        }
        if ($null -ne $Body) {
            $args.Body = ($Body | ConvertTo-Json -Depth 10)
        }

        $response = Invoke-RestMethod @args
        Write-Host "RESPONSE:"
        Write-Host ($response | ConvertTo-Json -Depth 20)
        return $response
    }
    catch {
        Write-Host "REST_EXCEPTION:"
        Write-Host $_.Exception.Message
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            Write-Host $_.ErrorDetails.Message
        }
        return $null
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
        Write-Host "JSON_PARSE_EXCEPTION:"
        Write-Host $_.Exception.Message
        return $null
    }
}

function Wait-ForPipelineSettled {
    param(
        [int]$MinimumDocuments,
        [int]$TimeoutSeconds
    )

    Write-Section "POLL: pipeline completion"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0

    while ((Get-Date) -lt $deadline) {
        $attempt += 1
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
            Write-Host "EMBEDDED_COUNT=$embedded"
            Write-Host "FETCHED_COUNT=$fetched"
            Write-Host "CHUNKED_COUNT=$chunked"
            Write-Host "TOTAL_DOCUMENTS=$($snapshot.total_documents)"
            if ($snapshot.total_documents -ge $MinimumDocuments -and $fetched -eq 0 -and $chunked -eq 0) {
                Write-Host "POLL_RESULT=pipeline_settled"
                return
            }
        }
        Start-Sleep -Seconds 5
    }

    Write-Host "POLL_RESULT=timeout"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$script:Nexus = Join-Path $RepoRoot ".venv\Scripts\nexus.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing venv Python: $Python"
}
if (-not (Test-Path -LiteralPath $script:Nexus)) {
    throw "Missing Nexus CLI: $script:Nexus"
}

Import-DotEnv -Path (Join-Path $RepoRoot ".env")

Write-Section "RUN CONTEXT"
Write-Host "TIMESTAMP=$((Get-Date).ToString('o'))"
Write-Host "REPO_ROOT=$RepoRoot"
Write-Host "API_URL=$ApiUrl"
Write-Host "DATABASE_URL=$env:DATABASE_URL"
Write-Host "PYTHON=$Python"
Write-Host "NEXUS=$script:Nexus"
Write-Host "SKIP_RSS=$SkipRss"

Write-Section "API HEALTH"
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "$ApiUrl/health" -TimeoutSec 10).Content
}
catch {
    Write-Host "API_HEALTH_EXCEPTION:"
    Write-Host $_.Exception.Message
    throw "API is not reachable at $ApiUrl"
}

Invoke-RawExe -Label "BEFORE RESET: nexus status" -Exe $script:Nexus -Arguments @("status")

Write-Section "RESET: truncate Nexus data tables"
$resetCode = @'
import asyncio
import os
from sqlalchemy import text
from app.db.session import make_engine

async def main():
    database_url = os.environ["DATABASE_URL"]
    engine = make_engine(database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("""
                TRUNCATE TABLE
                    claim_evidence,
                    claims,
                    brief_items,
                    briefs,
                    agent_runs,
                    spans,
                    documents,
                    sources
                RESTART IDENTITY CASCADE
            """))
    finally:
        await engine.dispose()
    print("RESET_OK")

asyncio.run(main())
'@
$ResetPy = Join-Path ([System.IO.Path]::GetTempPath()) ("nexus-reset-" + [Guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $ResetPy -Value $resetCode -Encoding UTF8
Write-Host "RESET_HELPER=$ResetPy"
& $Python $ResetPy
if ($LASTEXITCODE -ne 0) {
    throw "Database reset failed with exit code $LASTEXITCODE"
}

Invoke-RawExe -Label "AFTER RESET: nexus status --json" -Exe $script:Nexus -Arguments @("status", "--json")
Invoke-RawExe -Label "AFTER RESET: nexus sources --json" -Exe $script:Nexus -Arguments @("sources", "--json")
Invoke-RawExe -Label "AFTER RESET: nexus documents --json" -Exe $script:Nexus -Arguments @("documents", "--json", "--limit", "100")

$FixtureDir = Join-Path ([System.IO.Path]::GetTempPath()) ("nexus-phase2-validation-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $FixtureDir | Out-Null

$fixtures = @(
    @{
        Title = "Validation Note - Retrieval Foundation"
        File = Join-Path $FixtureDir "retrieval-foundation.md"
        Source = "validation_text_retrieval"
        Text = @"
Nexus validation fixture for local embeddings and semantic retrieval.
This document describes the Phase 2 retrieval foundation: clean source text is split into spans, each span receives a BAAI bge-small embedding vector, and pgvector stores those vectors for cosine search.
The expected operator behavior is that this note moves from fetched to chunked to embedded and becomes available through nexus search for queries about local embeddings, vector search, semantic retrieval, and span inspection.
"@
    },
    @{
        Title = "Validation Note - Operations"
        File = Join-Path $FixtureDir "operations.md"
        Source = "validation_text_operations"
        Text = @"
Nexus validation fixture for operations and pipeline health.
Operators should be able to inspect status counts, list sources, list documents by status, inspect a single document, and verify whether spans have vector embeddings.
The robust implementation should keep stuck fetched or chunked documents visible and should let a production operator identify whether ingestion, chunking, or embedding is the failing stage.
"@
    },
    @{
        Title = "Validation Note - Domain Packs"
        File = Join-Path $FixtureDir "domain-packs.md"
        Source = "validation_text_domain"
        Text = @"
Nexus validation fixture for domain pack routing and source metadata.
The personal_ai_tech domain pack groups research notes, RSS articles, product releases, infrastructure updates, and AI tooling observations.
This text should be ingested as a manual source with provenance, searchable content, a stored content hash, and generated span embeddings.
"@
    }
)

Write-Section "TEXT FIXTURES"
foreach ($fixture in $fixtures) {
    Set-Content -LiteralPath $fixture.File -Value $fixture.Text -Encoding UTF8
    Write-Host "FIXTURE_FILE=$($fixture.File)"
    Write-Host "FIXTURE_TITLE=$($fixture.Title)"
    Write-Host "FIXTURE_SOURCE=$($fixture.Source)"
}

foreach ($fixture in $fixtures) {
    Invoke-RawExe `
        -Label "INGEST TEXT: $($fixture.Title)" `
        -Exe $script:Nexus `
        -Arguments @(
            "ingest",
            "text",
            "--title",
            $fixture.Title,
            "--file",
            $fixture.File,
            "--source-name",
            $fixture.Source,
            "--domain-pack",
            "personal_ai_tech",
            "--json"
        )
}

$rssSources = @(
    @{
        Name = "validation_reddit_python"
        Url = "https://www.reddit.com/r/Python/.rss"
    },
    @{
        Name = "validation_hn_frontpage"
        Url = "https://hnrss.org/frontpage"
    }
)

if (-not $SkipRss) {
    foreach ($rss in $rssSources) {
        $source = Invoke-RawRestJson `
            -Label "CREATE RSS SOURCE: $($rss.Name)" `
            -Method "Post" `
            -Uri "$ApiUrl/sources" `
            -Body @{
                name = $rss.Name
                source_type = "rss"
                url = $rss.Url
                domain_pack = "personal_ai_tech"
                enabled = $true
                credibility_score = 0.8
            }

        if ($null -ne $source -and $source.id) {
            Invoke-RawExe `
                -Label "INGEST RSS: $($rss.Name)" `
                -Exe $script:Nexus `
                -Arguments @("ingest", "rss", $source.id, "--json")
        }
        else {
            Write-Host "RSS_SOURCE_CREATE_FAILED=$($rss.Name)"
        }
    }
}

Wait-ForPipelineSettled -MinimumDocuments 3 -TimeoutSeconds $EmbeddingWaitSeconds

Invoke-RawExe -Label "FINAL: nexus status" -Exe $script:Nexus -Arguments @("status")
Invoke-RawExe -Label "FINAL: nexus status --json" -Exe $script:Nexus -Arguments @("status", "--json")
Invoke-RawExe -Label "FINAL: nexus sources --json" -Exe $script:Nexus -Arguments @("sources", "--json")

Write-Section "FINAL: nexus documents --json"
$documents = Invoke-NexusJson -Arguments @("documents", "--json", "--limit", "100")

if ($null -ne $documents) {
    foreach ($doc in @($documents | Select-Object -First 8)) {
        Invoke-RawExe `
            -Label "DETAIL: nexus document $($doc.id)" `
            -Exe $script:Nexus `
            -Arguments @("document", $doc.id)
    }
}

$searches = @(
    "local embeddings semantic retrieval",
    "pipeline health fetched chunked embedded status",
    "domain pack AI tooling observations",
    "Python Reddit RSS feed",
    "Hacker News frontpage RSS"
)

foreach ($query in $searches) {
    Invoke-RawExe `
        -Label "SEARCH: $query" `
        -Exe $script:Nexus `
        -Arguments @("search", $query, "--top-k", "5", "--json")
}

Write-Section "SCRIPT COMPLETE"
Write-Host "TIMESTAMP=$((Get-Date).ToString('o'))"
Write-Host "FIXTURE_DIR=$FixtureDir"
