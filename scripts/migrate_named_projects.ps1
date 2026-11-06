# 两本已获授权的旧目录受控迁移；不修改作品内部文件，不操作服务。
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ProjectsRoot,
    [Parameter(Mandatory=$true)][string]$BackupRoot
)

$ErrorActionPreference = 'Stop'
$projectsPath = [IO.Path]::GetFullPath($ProjectsRoot)
$backupPath = [IO.Path]::GetFullPath($BackupRoot)
if ($PSVersionTable.PSVersion.Major -lt 7) { throw '需要PowerShell 7及以上版本' }
if (-not (Test-Path -LiteralPath $projectsPath -PathType Container)) { throw '作品根不存在' }
if ((Get-Item -LiteralPath $projectsPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '拒绝链接作品根' }
if ($backupPath.StartsWith($projectsPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw '备份必须在作品根之外' }
if (Test-Path -LiteralPath $backupPath) { throw '备份目标已占用' }

function Get-Inventory([string]$Root) {
    $items = @(Get-ChildItem -LiteralPath $Root -Recurse -Force)
    if (@($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw '目录内存在链接，拒绝复制或迁移' }
    $files = @($items | Where-Object { -not $_.PSIsContainer } | Sort-Object FullName | ForEach-Object {
        [ordered]@{ Relative=[IO.Path]::GetRelativePath($Root, $_.FullName).Replace('\','/'); Length=$_.Length;
                    SHA256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); LastWriteTimeUtcTicks=$_.LastWriteTimeUtc.Ticks }
    })
    $directories = @($items | Where-Object PSIsContainer | Sort-Object FullName | ForEach-Object { [IO.Path]::GetRelativePath($Root, $_.FullName).Replace('\','/') })
    return [ordered]@{ Files=$files; Directories=$directories }
}

function Get-InventoryHash($Inventory) {
    $json = ConvertTo-Json -InputObject $Inventory -Depth 8 -Compress
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($json))).ToLowerInvariant()
}

function Assert-Inactive([string]$Root) {
    $sessions = Join-Path $Root '.creative_os/agent/conversations'
    if (Test-Path -LiteralPath $sessions) {
        foreach ($file in Get-ChildItem -LiteralPath $sessions -Filter '*.json' -File -Force) {
            $session = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json -AsHashtable
            if ($session.jobs -isnot [System.Collections.IDictionary]) { throw '会话任务结构不明，拒绝迁移' }
            foreach ($job in $session.jobs.Values) {
                if ($job.status -notin @('completed','failed')) { throw '存在活动任务，拒绝迁移' }
            }
        }
    }
    $receipts = Join-Path $Root '.creative_os/commands/results.json'
    if (Test-Path -LiteralPath $receipts) {
        $commands = Get-Content -LiteralPath $receipts -Raw | ConvertFrom-Json -AsHashtable
        if ($commands.records -isnot [System.Collections.IDictionary]) { throw '命令回执结构不明，拒绝迁移' }
        if (@($commands.records.Values | Where-Object { $_.state -eq 'reserved' }).Count) { throw '存在待核对写操作，拒绝迁移' }
    }
}

$plans = @(
    @{Old='validation_novel'; New='雾城回声'; Id='novel-validation-001'},
    @{Old='novel_domain_validation'; New='末班钟表店'; Id='novel-domain-validation'}
)
# 全部预检通过后才创建备份；任何目标被占用都不能搬动另一本。
foreach ($plan in $plans) {
    $plan.Source = [IO.Path]::GetFullPath((Join-Path $projectsPath $plan.Old))
    $plan.Target = [IO.Path]::GetFullPath((Join-Path $projectsPath $plan.New))
    if ([IO.Path]::GetDirectoryName($plan.Source) -ne $projectsPath -or [IO.Path]::GetDirectoryName($plan.Target) -ne $projectsPath) { throw '最终绝对路径不在指定作品根' }
    if (-not (Test-Path -LiteralPath $plan.Source -PathType Container) -or (Test-Path -LiteralPath $plan.Target)) { throw '源目录不存在或目标已占用' }
    if ((Get-Item -LiteralPath $plan.Source -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '源目录是链接' }
    $metadata = Get-Content -LiteralPath (Join-Path $plan.Source 'project.json') -Raw | ConvertFrom-Json
    if ($metadata.id -cne $plan.Id) { throw '稳定ID不符，拒绝迁移' }
    Assert-Inactive $plan.Source
    $plan.Inventory = Get-Inventory $plan.Source
    $plan.Hash = Get-InventoryHash $plan.Inventory
}

New-Item -ItemType Directory -Path $backupPath | Out-Null
foreach ($plan in $plans) {
    $saved = Join-Path $backupPath $plan.Old
    Copy-Item -LiteralPath $plan.Source -Destination $saved -Recurse -Force
    if ((Get-InventoryHash (Get-Inventory $saved)) -cne $plan.Hash) { throw '备份校验失败，未执行移动' }
    [ordered]@{ Source=$plan.Source; Target=$plan.Target; StableId=$plan.Id; InventorySHA256=$plan.Hash; Inventory=$plan.Inventory } |
        ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $backupPath ($plan.Old + '.manifest.json')) -Encoding utf8
}

# 两份备份均通过后，再核查活动任务、源清单和目标空缺；不覆盖、不删除。
foreach ($plan in $plans) {
    Assert-Inactive $plan.Source
    if ((Test-Path -LiteralPath $plan.Target) -or (Get-InventoryHash (Get-Inventory $plan.Source)) -cne $plan.Hash) { throw '备份后状态发生变化，停止迁移' }
}
$completed = @()
foreach ($plan in $plans) {
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($plan.Source)) -ne $projectsPath -or [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($plan.Target)) -ne $projectsPath) { throw '移动路径校验失败' }
    Assert-Inactive $plan.Source
    if (Test-Path -LiteralPath $plan.Target) { throw '移动前目标被占用，停止迁移' }
    Move-Item -LiteralPath $plan.Source -Destination $plan.Target
    if ((Get-InventoryHash (Get-Inventory $plan.Target)) -cne $plan.Hash) { throw '迁后校验失败，保留完整备份，需人工核对' }
    $completed += [ordered]@{ Source=$plan.Source; Target=$plan.Target; StableId=$plan.Id; InventorySHA256=$plan.Hash;
                            FileCount=@($plan.Inventory.Files).Count; DirectoryCount=@($plan.Inventory.Directories).Count }
}
[ordered]@{ Status='verified'; BackupRoot=$backupPath; Projects=$completed } | ConvertTo-Json -Depth 6
