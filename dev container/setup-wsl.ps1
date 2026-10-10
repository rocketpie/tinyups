#Requires -Version 7
$ErrorActionPreference = "Stop"

Set-strictMode -Version Latest

$Distro = "Ubuntu-24.04"

"Update WSL..."
wsl --update

"Checking for '$Distro'..."
$installed = wsl --list --quiet |
    ForEach-Object { $_.Trim([char]0).Trim() }

if ($installed -notcontains $Distro) {
    "Installing '$Distro'..."

    wsl --install -d $Distro

    ""
    "If Windows requests a reboot, reboot now."
    "in any case, run this script again."
    exit
}

"Set default distro to '$Distro'..."
wsl --set-default $Distro

""
"'$Distro' is installed and configured as the default WSL distro."
"now run:"
"> wsl"
"and create your Linux user when prompted."
""
"Then run the Linux bootstrap:"
"> bash '$(wsl wslpath -a (join-path $psscriptroot 'bootstrap-wsl.sh'))'"