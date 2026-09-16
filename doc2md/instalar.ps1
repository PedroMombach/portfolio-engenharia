<#
    instalar.ps1 — cria o ambiente do Doc2MD numa maquina nova, do zero.

    USO:
      .\instalar.ps1                      -> cria (ou atualiza) o ambiente 'doc2md' e confere
      .\instalar.ps1 -Nome outro-nome     -> usa outro nome de ambiente
      .\instalar.ps1 -Idiomas por,deu,eng -> pacotes de idioma do Tesseract a baixar
      .\instalar.ps1 -Melhores            -> baixa os modelos 'tessdata_best' (mais lentos e
                                             mais precisos; podem ajudar em scans antigos)
      .\instalar.ps1 -Gpu                 -> troca o torch pelo build CUDA (requirements-gpu.txt).
                                             So faz sentido com GPU NVIDIA; medido numa RTX 3050
                                             de 6 GB, os modelos do Docling ficam 16x mais rapidos

    O que ele faz, na ordem:
      1. acha o conda (PATH, miniconda3 ou anaconda3 no perfil do usuario);
      2. cria o ambiente a partir do environment.yml, ou o atualiza se ja existir;
      3. baixa os .traineddata que faltarem para o tessdata DO AMBIENTE (sem exigir
         administrador, ao contrario da instalacao do Tesseract em Program Files);
      4. roda `python main.py doutor` e devolve o codigo de saida dele.

    Nao instala nada fora do ambiente conda e nao toca no acervo.
#>
[CmdletBinding()]
param(
    [string]$Nome = "doc2md",
    [string[]]$Idiomas = @("por", "deu", "eng"),
    [switch]$Melhores,
    [switch]$Gpu
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$yml = Join-Path $raiz "environment.yml"
if (-not (Test-Path -LiteralPath $yml)) { throw "environment.yml nao encontrado em $raiz" }

# --- 1. conda ---------------------------------------------------------------------------------
$conda = (Get-Command conda -ErrorAction SilentlyContinue).Source
if (-not $conda) {
    foreach ($p in @("$env:USERPROFILE\miniconda3\Scripts\conda.exe",
                     "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
                     "$env:LOCALAPPDATA\miniconda3\Scripts\conda.exe",
                     "C:\ProgramData\miniconda3\Scripts\conda.exe")) {
        if (Test-Path -LiteralPath $p) { $conda = $p; break }
    }
}
if (-not $conda) {
    throw "conda nao encontrado. Instale o Miniconda (https://docs.conda.io/projects/miniconda) e rode de novo."
}
Write-Host "conda: $conda" -ForegroundColor Cyan

# --- 2. ambiente ------------------------------------------------------------------------------
$existe = (& $conda env list) | Select-String -Pattern "^\s*$([regex]::Escape($Nome))\s"
if ($existe) {
    Write-Host "ambiente '$Nome' ja existe: atualizando a partir do environment.yml" -ForegroundColor Cyan
    & $conda env update -n $Nome -f $yml --prune
} else {
    Write-Host "criando o ambiente '$Nome' (baixa torch e modelos do Docling: va tomar um cafe)" -ForegroundColor Cyan
    & $conda env create -n $Nome -f $yml
}
if ($LASTEXITCODE -ne 0) { throw "conda falhou (codigo $LASTEXITCODE)" }

if ($Gpu) {
    # Troca o torch pelo build CUDA. Medido numa RTX 3050 6 GB: 16x nos modelos do Docling.
    Write-Host "instalando o torch com CUDA (requirements-gpu.txt)" -ForegroundColor Cyan
    & $conda run -n $Nome --no-capture-output python -m pip install -r (Join-Path $raiz "requirements-gpu.txt")
    if ($LASTEXITCODE -ne 0) { throw "falha ao instalar o torch CUDA (codigo $LASTEXITCODE)" }
}

$prefixo = (& $conda run -n $Nome python -c "import sys; print(sys.prefix)").Trim()
if (-not $prefixo) { throw "nao consegui descobrir o diretorio do ambiente '$Nome'" }
Write-Host "ambiente em: $prefixo" -ForegroundColor Cyan

# --- 3. idiomas do Tesseract ------------------------------------------------------------------
# O conda instala o motor, nao os idiomas. O Tesseract so acha o tessdata quando TESSDATA_PREFIX
# esta definido — a ferramenta deduz isso sozinha (nucleo/ambiente.py), mas os arquivos precisam
# estar no lugar certo.
$tessdata = Join-Path $prefixo "share\tessdata"
if (-not (Test-Path -LiteralPath $tessdata)) { $tessdata = Join-Path $prefixo "Library\share\tessdata" }
if (-not (Test-Path -LiteralPath $tessdata)) { New-Item -ItemType Directory -Force -Path $tessdata | Out-Null }

# O pacote conda-forge do Windows separa os idiomas (share\tessdata) dos arquivos de
# configuracao (Library\share\tessdata\configs). Com os dois em lugares diferentes, o `-l por`
# funciona e a saida tsv/pdf morre com TesseractConfigError. Junta tudo no diretorio de idiomas.
$configs = Join-Path $prefixo "Library\share\tessdata"
if (($configs -ne $tessdata) -and (Test-Path -LiteralPath (Join-Path $configs "configs"))) {
    foreach ($pasta in @("configs", "tessconfigs")) {
        $origem = Join-Path $configs $pasta
        if ((Test-Path -LiteralPath $origem) -and -not (Test-Path -LiteralPath (Join-Path $tessdata $pasta))) {
            Write-Host "[ajuste   ] copiando $pasta para $tessdata" -ForegroundColor DarkGray
            Copy-Item -LiteralPath $origem -Destination $tessdata -Recurse -Force
        }
    }
}

$repo = if ($Melhores) { "tessdata_best" } else { "tessdata" }
foreach ($idioma in $Idiomas) {
    $destino = Join-Path $tessdata "$idioma.traineddata"
    if ((Test-Path -LiteralPath $destino) -and (Get-Item -LiteralPath $destino).Length -gt 1MB) {
        Write-Host ("[ja existe] {0}.traineddata" -f $idioma) -ForegroundColor DarkGray
        continue
    }
    $url = "https://github.com/tesseract-ocr/$repo/raw/main/$idioma.traineddata"
    Write-Host ("[baixando ] {0}.traineddata ({1})" -f $idioma, $repo) -ForegroundColor Cyan
    $tmp = "$destino.parcial"
    try {
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        if ((Get-Item -LiteralPath $tmp).Length -lt 1MB) { throw "arquivo baixado e pequeno demais" }
        Move-Item -LiteralPath $tmp -Destination $destino -Force
    } catch {
        Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
        Write-Host ("[FALHOU   ] {0}: {1}" -f $idioma, $_.Exception.Message) -ForegroundColor Red
        Write-Host ("             baixe a mao de {0} para {1}" -f $url, $tessdata) -ForegroundColor Red
    }
}

# --- 4. conferencia ---------------------------------------------------------------------------
Write-Host "`n=== python main.py doutor ===" -ForegroundColor Cyan
& $conda run -n $Nome --no-capture-output python (Join-Path $raiz "main.py") doutor
$rc = $LASTEXITCODE
if ($rc -eq 0) {
    Write-Host "`nAmbiente pronto. Proximo passo: conda activate $Nome; python main.py init" -ForegroundColor Green
} else {
    Write-Host "`nO doutor apontou pendencias acima (codigo $rc). Resolva e rode de novo." -ForegroundColor Yellow
}
exit $rc
