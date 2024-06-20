function Is-Admin() {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function main() {
    if (-not (Is-Admin)) {
        Write-Host "error: administrator privileges required"
        return 1
    }

    if (Test-Path ".\build\") {
        Remove-Item -Path ".\build\" -Recurse -Force
    }

    mkdir ".\build\"

    # entrypoint relative to .\build\pyinstaller\
    $entryPoint = "..\..\service_list_builder\main.py"

    # create folder structure
    mkdir ".\build\service-list-builder\"

    # pack executable
    mkdir ".\build\pyinstaller\"
    Push-Location ".\build\pyinstaller\"
    pyinstaller $entryPoint --onefile --name service-list-builder
    Pop-Location

    # create final package
    Copy-Item ".\build\pyinstaller\dist\service-list-builder.exe" ".\build\service-list-builder\"
    Copy-Item ".\service_list_builder\lists.ini" ".\build\service-list-builder\"
    Copy-Item ".\service_list_builder\NSudo\NSudoLG.exe" ".\build\service-list-builder\"

    return 0
}

$_exitCode = main
Write-Host # new line
exit $_exitCode
