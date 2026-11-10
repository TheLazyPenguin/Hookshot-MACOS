"""Hit-test the production WPF building footer offscreen, without starting the Builder or opening a window."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

RUN_ALL_ARGS = ["--dotnet", "{dotnet}"]
RUN_ALL_SKIP = {"linux": "WPF layout and hit testing require Windows; exercised by the Windows source checks"}

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--dotnet", default="dotnet")
    parser.add_argument("--artifacts", type=Path, help="copy measurements and unmodified offscreen PNGs to a fresh local directory")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("this fixture needs native Windows WPF")
    dotnet = shutil.which(args.dotnet)
    if not dotnet:
        parser.error(".NET 8 SDK is required")
    if args.artifacts and args.artifacts.exists():
        parser.error("artifact directory already exists; preserve the earlier run")
    flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    builder = args.source / "builder/HookshotBuilder"
    with tempfile.TemporaryDirectory(prefix="builder-details-hitbox-") as folder:
        root = Path(folder)
        inputs, output = root / "source", root / "output"
        inputs.mkdir()
        for name in ("App.xaml", "MainWindow.xaml"):
            shutil.copyfile(builder / name, inputs / name)
        fonts = root / "Fonts"
        fonts.mkdir()
        for path in sorted((builder / "Fonts").glob("*.ttf")):
            shutil.copyfile(path, fonts / path.name)
        (root / "Program.cs").write_text((ROOT / "tests/builder_details_hitbox_test.cs").read_text(encoding="utf-8"), encoding="utf-8")
        (root / "NuGet.Config").write_text("<configuration><packageSources><clear/></packageSources></configuration>\n", encoding="utf-8")
        (root / "Fixture.csproj").write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net8.0-windows</TargetFramework><UseWPF>true</UseWPF>
<EnableDefaultPageItems>false</EnableDefaultPageItems><EnableDefaultApplicationDefinition>false</EnableDefaultApplicationDefinition>
<Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings><TreatWarningsAsErrors>true</TreatWarningsAsErrors>
<UseSharedCompilation>false</UseSharedCompilation><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Resource Include="Fonts\\*.ttf" /></ItemGroup></Project>\n''', encoding="utf-8")
        # This compiles the fixture and production font resources, not App.xaml/MainWindow.xaml code-behind.
        subprocess.run([dotnet, "restore", str(root / "Fixture.csproj"), "--configfile", str(root / "NuGet.Config"),
                        "--disable-parallel"], check=True, creationflags=flags)
        subprocess.run([dotnet, "build", str(root / "Fixture.csproj"), "--configuration", "Release",
                        "--no-restore", "--disable-build-servers", "-maxcpucount:1", "-nodeReuse:false"],
                       check=True, creationflags=flags)
        ran = subprocess.run([dotnet, str(root / "bin/Release/net8.0-windows/Fixture.dll"), str(inputs), str(output)],
                             check=False, creationflags=flags)
        # The behavior result remains authoritative; a compiler/XAML exception cannot masquerade as a negative hit-test.
        result_file = output / "hitbox-result.json"
        if not result_file.is_file():
            raise RuntimeError("the offscreen fixture did not produce a behavioral result")
        result = json.loads(result_file.read_text(encoding="utf-8"))
        if args.artifacts:
            shutil.copytree(output, args.artifacts)
        expected = int(result["negativeBlankExpectationsFailed"] != 0)
        if ran.returncode != expected:
            raise RuntimeError(f"unexpected offscreen exit {ran.returncode}; behavioral result expected {expected}")
        return ran.returncode


if __name__ == "__main__":
    raise SystemExit(main())
