# Installe (ou retire) la tache planifiee qui lance tools/sonde_sante.py toutes les heures.
#
#   powershell -File tools\installer_sonde_sante.ps1              # installe / met a jour
#   powershell -File tools\installer_sonde_sante.ps1 -Retirer     # retire
#
# La tache tourne dans la session de l'utilisateur (pas de droits admin) : c'est ce qui
# permet a la notification Windows de s'afficher. pythonw : aucune fenetre ne clignote.
# Docker arrete n'est pas signale (AutoStart coupe expres) : voir l'en-tete de la sonde.
param(
    [switch]$Retirer,
    [string]$Python = ""
)
$ErrorActionPreference = 'Stop'
$nom = 'Sonde sante'
$dossier = '\BotDiscord\'
$racine = Split-Path -Parent $PSScriptRoot

if ($Retirer) {
    Unregister-ScheduledTask -TaskName $nom -TaskPath $dossier -Confirm:$false
    Write-Output "Tache $dossier$nom retiree."
    return
}

if (-not $Python) {
    $cmd = Get-Command pythonw.exe -All -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notmatch 'WindowsApps|[\\/]\.venv[\\/]' } | Select-Object -First 1
    if (-not $cmd) { throw "pythonw.exe introuvable : passer -Python <chemin de pythonw.exe>" }
    $Python = $cmd.Source
}

$action = New-ScheduledTaskAction -Execute $Python `
    -Argument "`"$racine\tools\sonde_sante.py`" --notifier" -WorkingDirectory $racine
$declencheur = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
$reglages = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $nom -TaskPath $dossier -Action $action -Trigger $declencheur `
    -Settings $reglages -Force `
    -Description 'Bots Discord : conteneurs, sauvegarde et liens d''invitation (tools/sonde_sante.py)' | Out-Null
Write-Output "Tache $dossier$nom installee : $Python, toutes les heures."
