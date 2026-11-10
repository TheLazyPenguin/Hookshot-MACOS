"""Exercise the actual Windows updater with authored HTTP/launch/temp-directory boundaries only."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUN_ALL_ARGS = ["--dotnet", "{dotnet}"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--dotnet", default="dotnet")
    args = parser.parse_args()
    dotnet = shutil.which(args.dotnet)
    if not dotnet:
        parser.error(".NET 8 SDK is required")
    source = (args.source / "builder/HookshotBuilder/Updater.cs").read_text(encoding="utf-8")
    # Compile the entire real class. Aliases replace only external boundaries, never its control flow or validation.
    aliases = """using HttpClient = DigestFixture.FakeHttpClient;
using Process = DigestFixture.FakeProcess;
using Environment = DigestFixture.FakeEnvironment;
using AppContext = DigestFixture.FakeAppContext;
"""
    fixture = (ROOT / "tests/updater_asset_digest_test.cs").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="updater-digest-build-") as folder:
        root = Path(folder)
        (root / "Updater.cs").write_text(aliases + source, encoding="utf-8")
        (root / "Program.cs").write_text(fixture, encoding="utf-8")
        (root / "NuGet.Config").write_text("<configuration><packageSources><clear/></packageSources></configuration>", encoding="utf-8")
        (root / "Fixture.csproj").write_text("""<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings>
<Nullable>enable</Nullable><TreatWarningsAsErrors>true</TreatWarningsAsErrors><NuGetAudit>false</NuGetAudit>
<UseSharedCompilation>false</UseSharedCompilation>
</PropertyGroup></Project>""", encoding="utf-8")
        subprocess.run([dotnet, "run", "--project", str(root / "Fixture.csproj"), "--configuration", "Release",
                        "--disable-build-servers"], check=True)


if __name__ == "__main__":
    main()
