"""Run the Windows Builder's actual update decision without WPF, a game, downloads or NVIDIA's SDK."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

RUN_ALL_ARGS = ["--dotnet", "{dotnet}"]
RUN_ALL_SKIP = {"linux": "Windows Builder update policy; .NET 8 fixture exercised on Windows"}

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--dotnet", default="dotnet")
    a = p.parse_args()
    dotnet = shutil.which(a.dotnet)
    if not dotnet:
        p.error(".NET 8 SDK is required for the Windows Builder update fixture")
    source = (a.source / "builder/HookshotBuilder/MainWindow.xaml.cs").read_text(encoding="utf-8")
    start = source.index("    internal void UpdateBuild(")
    end = source.index("    // ================= the window", start)
    fixture = (ROOT / "tests/builder_dlss_update_test.cs").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="builder-dlss-update-") as folder:
        root = Path(folder)
        (root / "Program.cs").write_text(fixture.replace("/* ACTUAL_UPDATE */", source[start:end]), encoding="utf-8")
        for name in ("BuilderSettings.cs", "ShaderStep.cs"):
            shutil.copyfile(a.source / "builder/HookshotBuilder" / name, root / name)
        (root / "NuGet.Config").write_text("<configuration><packageSources><clear/></packageSources></configuration>", encoding="utf-8")
        (root / "Fixture.csproj").write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings>
<Nullable>enable</Nullable><TreatWarningsAsErrors>true</TreatWarningsAsErrors><NuGetAudit>false</NuGetAudit>
</PropertyGroup></Project>''', encoding="utf-8")
        subprocess.run([dotnet, "run", "--project", str(root / "Fixture.csproj"), "--configuration", "Release"], check=True)


if __name__ == "__main__":
    main()
