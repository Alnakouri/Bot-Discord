# Attend la cle Groq dans le presse-papiers, la verifie, puis l'enregistre sur le Worker.
# Elle n'est jamais affichee. L'attente evite de l'ecraser en copiant la commande qui lance ce script.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$limite = (Get-Date).AddSeconds(90)
do {
  $cle = ([string](Get-Clipboard -Raw)).Trim()
  if ($cle.StartsWith('gsk_')) { break }
  Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $limite)

$lignes = ($cle -split '\r?\n').Count
"Presse-papiers : $($cle.Length) caracteres, $lignes ligne(s), debut gsk_ : $($cle.StartsWith('gsk_'))"

if ($cle -cnotmatch '^gsk_[\x21-\x7E]{20,}$') {
  'ECHEC : ce n''est pas une cle Groq complete. Rien n''a ete enregistre.'
  exit 1
}

try {
  $reponse = Invoke-WebRequest 'https://api.groq.com/openai/v1/models' -UseBasicParsing -Headers @{ Authorization = "Bearer $cle" }
} catch {
  "ECHEC : Groq refuse cette cle (HTTP $($_.Exception.Response.StatusCode.value__)). Rien n'a ete enregistre."
  exit 1
}

$modeles = ($reponse.Content | ConvertFrom-Json).data.id
"Groq accepte la cle. gpt-oss-20b : $($modeles -contains 'openai/gpt-oss-20b'), gpt-oss-120b : $($modeles -contains 'openai/gpt-oss-120b')"

$cle | npx wrangler@4 secret put GROQ_KEY_DEMO
if ($LASTEXITCODE -ne 0) {
  'ECHEC : Wrangler n''a pas enregistre la cle.'
  exit 1
}
'OK : cle enregistree et active sur le Worker.'
