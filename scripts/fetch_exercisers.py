"""Fetch the pinned CP/M 8080 exerciser programs into tests/exercisers/.

Nothing fetched here is committed. Every file is pinned by SHA-256 to the
bytes recorded in docs/validation.md, and each has two sources: an immutable
commit in superzazu/8080 on GitHub, and Mike Douglas's altairclone.com
directory, from which the GitHub copies were taken (the hashes are identical).
The immutable URL is tried first.

CPUTEST.COM (SuperSoft Associates, 1981) carries a copyright notice and no
license; it is fetched only with --include-cputest.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

GITHUB_REPOSITORY = "https://github.com/superzazu/8080"
GITHUB_REVISION = "274ffd700b81baabea99b0963bc1260b67132185"
GITHUB_RAW = f"https://raw.githubusercontent.com/superzazu/8080/{GITHUB_REVISION}/cpu_tests"
ALTAIRCLONE = "https://altairclone.com/downloads/cpu_tests"

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "tests" / "exercisers"


@dataclass(frozen=True)
class Artifact:
    name: str
    sha256: str
    size: int
    license: str
    default: bool = True


ARTIFACTS: tuple[Artifact, ...] = (
    # Ian Bartholomew's 8080 port of Frank Cringle's prelim/zexlax; GPL-2.0-or-later.
    Artifact("8080PRE.COM", "18eb3c79cba42c0718f160be6a1853cb64cdce7aa47d65780189a57bdd98c4e0", 1024, "GPL-2.0-or-later"),
    Artifact("8080PRE.MAC", "ca1507444929978038ad4f83d18e13bcce72072df2b850932b3982c31cfc1ccc", 4818, "GPL-2.0-or-later"),
    Artifact("8080EXER.COM", "8e1736b667c088ac63b69f20768a9a237f3cd739b4cb0ebea99b9e39d3ab1da4", 4608, "GPL-2.0-or-later"),
    Artifact("8080EXER.MAC", "ddf30299b87e7e244251f96f495d6e2946545a296af25675a8cdebc6478dbf9c", 29079, "GPL-2.0-or-later"),
    # Mike Douglas's May 2013 modification with the hardware CRCs compiled in.
    Artifact("8080EXM.COM", "6e3286e11bb1a8f47b8ee1280b4a067be813193363e3223c99b0d21912f44aeb", 4608, "GPL-2.0-or-later"),
    Artifact("8080EXM.MAC", "806d3a069b0021e9925c0b7c26fd74a3c397ca7f618a599ab4a8396ebcd1f3f3", 29411, "GPL-2.0-or-later"),
    # Microcosm Associates 1980, donated to the SIG/M CP/M user group; no formal license.
    Artifact("TST8080.COM", "9561c6fb6c99efe3de00eb77e4044fd102151058b39ac2d7bce10483838a08e7", 1536, "Microcosm 1980, SIG/M donation"),
    Artifact("TST8080.ASM", "d9f405470a0ec9bb9368bcbef015b0bbb326c3d673ce7ddfc48ba2d978e44940", 14657, "Microcosm 1980, SIG/M donation"),
    # SuperSoft Associates 1981, Diagnostics II; copyright, no license grant. Opt-in.
    Artifact("CPUTEST.COM", "e61a9a75348c774486c2207080ea4effbf6c2367fdace31b0731081a4144030b", 19200, "proprietary (SuperSoft 1981)", default=False),
)


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "i8080-python fetch_exercisers"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _install(data: bytes, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    with os.fdopen(fd, "wb") as output:
        output.write(data)
    os.chmod(temporary, 0o644)
    os.replace(temporary, target)


def fetch(artifact: Artifact, force: bool) -> str:
    target = DESTINATION / artifact.name
    if target.exists() and not force:
        actual = _sha256(target.read_bytes())
        if actual == artifact.sha256:
            return "present"
        raise RuntimeError(
            f"{target} exists with SHA-256 {actual}, expected {artifact.sha256}; "
            "delete it or pass --force"
        )
    errors: list[str] = []
    for base in (GITHUB_RAW, ALTAIRCLONE):
        url = f"{base}/{artifact.name}"
        try:
            data = _download(url)
        except OSError as error:
            errors.append(f"{url}: {error}")
            continue
        actual = _sha256(data)
        if actual != artifact.sha256:
            errors.append(f"{url}: SHA-256 {actual}, expected {artifact.sha256}")
            continue
        if len(data) != artifact.size:
            errors.append(f"{url}: {len(data)} bytes, expected {artifact.size}")
            continue
        _install(data, target)
        return f"fetched from {base}"
    raise RuntimeError(f"{artifact.name}: no source verified:\n  " + "\n  ".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--include-cputest",
        action="store_true",
        help="also fetch CPUTEST.COM (SuperSoft 1981, copyrighted, no license grant)",
    )
    parser.add_argument("--force", action="store_true", help="re-download files already present")
    args = parser.parse_args(argv)

    failures = 0
    for artifact in ARTIFACTS:
        if not artifact.default and not args.include_cputest:
            print(f"{artifact.name:14} skipped ({artifact.license}; pass --include-cputest)")
            continue
        try:
            status = fetch(artifact, args.force)
        except RuntimeError as error:
            failures += 1
            print(f"{artifact.name:14} FAILED: {error}", file=sys.stderr)
            continue
        print(f"{artifact.name:14} {status}; sha256 {artifact.sha256[:16]}... ok; {artifact.license}")
    print(f"destination: {DESTINATION} (gitignored; pinned to superzazu/8080@{GITHUB_REVISION[:12]})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
